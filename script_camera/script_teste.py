#!/usr/bin/env python3
# main_fixed_ids.py
# Requer: degirum, opencv, numpy e sua sort.py (mantenha no mesmo dir)
# Ajuste ZOO_PATH, LABELS_FILES e EXPECTED_SLOTS conforme seu setup.

import time
import cv2
import numpy as np
import degirum as dg
import json
from pprint import pprint
from sort import Sort

# --------------------
# Config
# --------------------
MODEL_NAME = "digitaldashv1"
ZOO_PATH = "/home/cepedi/hailo_examples/models/digitaldashv1/digitaldashv1.json"
LABELS_FILES = "/home/cepedi/hailo_examples/models/digitaldashv1/labels_coco.json"
CAMERA_ID = 0
CONF_THRESH = 0.35
INPUT_WH = (640, 640)

# Expected slots: list of tuples (label_or_class_id, count)
# You can use class_id (int) or label text (str). Here we use class_id integers (as your model returns).
# Example: class 0 -> cpu (1 slot), class 1 -> fan (2 slots), class 3 -> motherboard (1), class 5 -> ram (2)
EXPECTED_SLOTS = [
    (0, 1),  # cpu -> 1 slot
    (1, 2),  # fan -> 2 slots
    (3, 1),  # motherboard -> 1 slot
    (4, 1),  # pallet -> 1 slot
    (5, 2),  # ram -> 2 slots
]

# Mapper params
IOU_ASSIGN_THRESHOLD = 0.1    # IoU threshold to consider matching detection->track->slot
CENTROID_DIST_THRESHOLD = 200 # px threshold fallback by centroid distance
SLOT_RELEASE_FRAMES = 30      # frames after which unused slot considered free

# SORT tracker
tracker = Sort(max_age=60, min_hits=1, iou_threshold=0.3)

# --------------------
# Utilities
# --------------------
def iou(boxA, boxB):
    # boxes: [x1,y1,x2,y2]
    xA = max(boxA[0], boxB[0]); yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2]); yB = min(boxA[3], boxB[3])
    interW = max(0, xB - xA); interH = max(0, yB - yA)
    interArea = interW * interH
    areaA = max(0, boxA[2]-boxA[0]) * max(0, boxA[3]-boxA[1])
    areaB = max(0, boxB[2]-boxB[0]) * max(0, boxB[3]-boxB[1])
    denom = areaA + areaB - interArea
    if denom <= 0: return 0.0
    return interArea / denom

def centroid(box):
    return ((box[0]+box[2])/2.0, (box[1]+box[3])/2.0)

def l2(a,b):
    return np.hypot(a[0]-b[0], a[1]-b[1])

# --------------------
# Postprocess YOLOv8-like (adaptado ao seu output)
# --------------------
def postprocess_detection_results(detection_output, input_shape, num_classes, label_dictionary, confidence_threshold=0.3):
    """
    detection_output: numpy array shape (1, N) from model.results[0]['data']
    input_shape: model.input_shape[0] e.g. (1, 640, 640, 3)
    returns list of detections: {"bbox":[x1,y1,x2,y2], "score":, "category_id":, "label":}
    """
    batch, input_h, input_w, _ = input_shape
    out = detection_output.reshape(-1)
    detections = []
    idx = 0
    for class_id in range(num_classes):
        if idx >= len(out): break
        num = int(out[idx]); idx += 1
        for _ in range(num):
            if idx + 5 > len(out): break
            y_min = float(out[idx+0]); x_min = float(out[idx+1])
            y_max = float(out[idx+2]); x_max = float(out[idx+3])
            score = float(out[idx+4]); idx += 5
            if score < confidence_threshold: 
                continue
            # convert to pixel coords in input size
            x1 = x_min * input_w; y1 = y_min * input_h
            x2 = x_max * input_w; y2 = y_max * input_h
            detections.append({
                "bbox":[x1,y1,x2,y2],
                "score": score,
                "category_id": class_id,
                "label": label_dictionary.get(str(class_id), f"class_{class_id}")
            })
        # early exit if remaining zeros
        if idx >= len(out) or np.all(out[idx:] == 0):
            break
    return detections

# --------------------
# FixedIDMapper class
# --------------------
class FixedIDMapper:
    def __init__(self, expected_slots, labels_map):
        """
        expected_slots: list of (class_id, count)
        labels_map: dict mapping str(class_id) -> label
        """
        self.labels_map = labels_map
        # Build slots: list of dict {slot_id, class_id, label, last_bbox, occupied_by (track_id), last_seen_frame}
        self.slots = []
        for cls, count in expected_slots:
            for k in range(count):
                slot = {
                    "slot_id": f"{labels_map.get(str(cls), str(cls))}_{k+1}",
                    "class_id": cls,
                    "label": labels_map.get(str(cls), str(cls)),
                    "last_bbox": None,
                    "occupied_by": None,
                    "last_seen_frame": -9999
                }
                self.slots.append(slot)
        # map track_id -> slot index
        self.track_to_slot = {}
        self.frame_idx = 0

    def _find_detection_for_track(self, track_bbox, detections):
        # return detection with max IoU (and > threshold) or None
        best_iou, best_det = 0.0, None
        for d in detections:
            i = iou(track_bbox, d["bbox"])
            if i > best_iou:
                best_iou = i; best_det = d
        if best_iou >= IOU_ASSIGN_THRESHOLD:
            return best_det, best_iou
        # fallback by centroid dist
        best_dist, best_det2 = 1e9, None
        tc = centroid(track_bbox)
        for d in detections:
            dc = centroid(d["bbox"])
            dist = l2(tc, dc)
            if dist < best_dist:
                best_dist = dist; best_det2 = d
        if best_dist <= CENTROID_DIST_THRESHOLD:
            return best_det2, None
        return None, None

    def release_orphaned_slots(self, active_track_ids):
        # free slots whose occupied_by is not in active tracks
        for s in self.slots:
            if s["occupied_by"] is not None and s["occupied_by"] not in active_track_ids:
                # mark free
                s["occupied_by"] = None
                s["last_bbox"] = None
                s["last_seen_frame"] = -9999
        # also prune mapping
        self.track_to_slot = {t:si for t,si in self.track_to_slot.items() if t in active_track_ids}

    def step(self, tracks, detections):
        """
        tracks: list of arrays [x1,y1,x2,y2,track_id]
        detections: list of dicts (from postprocess) => used to get class_ids
        returns: list of enriched tracks: {track_id, sort_bbox, fixed_slot_id_or_None, label_or_None}
        """
        self.frame_idx += 1
        active_ids = [int(t[4]) for t in tracks] if len(tracks)>0 else []
        self.release_orphaned_slots(active_ids)

        enriched = []

        # For faster matching, build a copy of detections list (we won't remove detections, we only reference them)
        for t in tracks:
            x1,y1,x2,y2,track_id = map(float, t)
            track_id = int(track_id)
            track_bbox = [x1,y1,x2,y2]

            # If track already mapped, refresh slot if still valid
            if track_id in self.track_to_slot:
                slot_idx = self.track_to_slot[track_id]
                slot = self.slots[slot_idx]
                slot["last_bbox"] = track_bbox
                slot["last_seen_frame"] = self.frame_idx
                slot["occupied_by"] = track_id
                enriched.append({"track_id":track_id, "sort_bbox":track_bbox, "fixed_id":slot["slot_id"], "label":slot["label"]})
                continue

            # find detection best for this track
            det, best_iou = self._find_detection_for_track(track_bbox, detections)
            class_id = det["category_id"] if det is not None else None
            # now assign to a slot
            assigned_slot_idx = None

            if class_id is not None:
                # prefer free slot of same class
                free_candidates = [i for i,s in enumerate(self.slots) if (s["class_id"]==class_id and s["occupied_by"] is None)]
                if free_candidates:
                    # choose nearest by centroid to track
                    tc = centroid(track_bbox)
                    best_dist = 1e9; best_i=None
                    for i in free_candidates:
                        s = self.slots[i]
                        if s["last_bbox"] is None:
                            best_dist = -1; best_i = i; break
                        dcent = l2(tc, centroid(s["last_bbox"]))
                        if dcent < best_dist:
                            best_dist=dcent; best_i=i
                    assigned_slot_idx = best_i
                else:
                    # no free slots of this class. find best "owned" slot of same class (to try to reassign if close)
                    owned = [i for i,s in enumerate(self.slots) if s["class_id"]==class_id]
                    if owned:
                        # choose slot whose last bbox is closest
                        tc = centroid(track_bbox)
                        best_dist = 1e9; best_i=None
                        for i in owned:
                            s = self.slots[i]
                            if s["last_bbox"] is None:
                                best_dist = 1e9; best_i = i
                                continue
                            dcent = l2(tc, centroid(s["last_bbox"]))
                            if dcent < best_dist:
                                best_dist = dcent; best_i = i
                        # only reassign if reasonably close
                        if best_dist <= CENTROID_DIST_THRESHOLD:
                            assigned_slot_idx = best_i

            # If assigned, bind
            if assigned_slot_idx is not None:
                slot = self.slots[assigned_slot_idx]
                slot["occupied_by"] = track_id
                slot["last_bbox"] = track_bbox
                slot["last_seen_frame"] = self.frame_idx
                self.track_to_slot[track_id] = assigned_slot_idx
                enriched.append({"track_id":track_id, "sort_bbox":track_bbox, "fixed_id":slot["slot_id"], "label":slot["label"]})
            else:
                # no fixed slot assignment
                enriched.append({"track_id":track_id, "sort_bbox":track_bbox, "fixed_id":None, "label":None})

        # return enriched tracks
        return enriched

# --------------------
# Load labels and model
# --------------------
with open(LABELS_FILES, "r") as f:
    labels_map = json.load(f)

model = dg.load_model(
    model_name=MODEL_NAME,
    zoo_url=ZOO_PATH,
    inference_host_address="@local",
    token="",
    device_type="HAILORT/HAILO8"
)
print("✅ Modelo carregado!")

mapper = FixedIDMapper(EXPECTED_SLOTS, labels_map)

# --------------------
# Start camera
# --------------------
cap = cv2.VideoCapture(CAMERA_ID)
if not cap.isOpened():
    raise RuntimeError("Erro ao abrir a câmera")

frame_idx = 0
try:
    while True:
        frame_idx += 1
        ret, frame = cap.read()
        if not ret:
            break

        # preprocess
        frame_resized = cv2.resize(frame, INPUT_WH)
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        input_tensor = np.expand_dims(frame_rgb, axis=0)

        # inference
        result = model(input_tensor)
        # debug: print raw vector shape
        # pprint(result.results)

        # postprocess detections
        detections = postprocess_detection_results(
            result.results[0]["data"],
            model.input_shape[0],
            num_classes = max([int(k) for k in labels_map.keys()])+1,
            label_dictionary=labels_map,
            confidence_threshold=CONF_THRESH
        )

        # prepare SORT input: [x1,y1,x2,y2,score]
        dets_for_sort = []
        for d in detections:
            x1,y1,x2,y2 = d["bbox"]
            s = d["score"]
            dets_for_sort.append([x1,y1,x2,y2,s])
        dets_for_sort = np.array(dets_for_sort) if len(dets_for_sort)>0 else np.empty((0,5))

        # update tracker
        tracks = tracker.update(dets_for_sort)

        # mapper assigns fixed ids for tracks
        enriched = mapper.step(tracks, detections)

        # draw all detections (green) and enriched tracks
        for d in detections:
            x1,y1,x2,y2 = map(int, d["bbox"])
            cv2.rectangle(frame_resized, (x1,y1),(x2,y2), (0,200,0), 1)
            cv2.putText(frame_resized, f"{d['label']} {d['score']:.2f}", (x1,y1-6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,200,0),1)

        for e in enriched:
            x1,y1,x2,y2 = map(int, e["sort_bbox"])
            t_id = e["track_id"]
            fixed = e["fixed_id"]
            # blue SORT id
            cv2.rectangle(frame_resized, (x1,y1),(x2,y2), (255,0,0), 2)
            cv2.putText(frame_resized, f"S{t_id}", (x1,y2+12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0),1)
            if fixed is not None:
                cv2.putText(frame_resized, f"{fixed}", (x1,y1-12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,200),2)

        cv2.imshow("FixedIDs + SORT", frame_resized)
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("🛑 Encerrado")
