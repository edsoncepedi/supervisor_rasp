import numpy as np
from sort_core import Sort
import re
import copy
from collections import defaultdict

def postprocess_detection_results(detection_output, input_shape, num_classes, label_dictionary, confidence_threshold=0.3):
    """
    Process the raw output tensor to produce formatted detection results.
    
    Parameters:
        detection_output (numpy.ndarray): The flattened output tensor from the model containing detection results.
        input_shape (tuple): The shape of the input image in the format (batch, input_height, input_width, channels).
        num_classes (int): The number of object classes that the model predicts.
        label_dictionary (dict): Mapping of class IDs to class labels.
        confidence_threshold (float, optional): Minimum confidence score required to keep a detection. Defaults to 0.3.

    Returns:
        list: List of dictionaries containing detection results in JSON-friendly format.
    """
    # Unpack input dimensions (batch is unused, but included for flexibility)
    batch, input_height, input_width, _ = input_shape
    
    # Initialize an empty list to store detection results
    new_inference_results = []

    # Reshape and flatten the raw output tensor for parsing
    output_array = detection_output.reshape(-1)

    # Initialize an index pointer to traverse the output array
    index = 0

    # Loop through each class ID to process its detections
    for class_id in range(num_classes):
        # Read the number of detections for this class from the output array
        num_detections = int(output_array[index])
        index += 1  # Move to the next entry in the array

        # Skip processing if there are no detections for this class
        if num_detections == 0:
            continue

        # Iterate through each detection for this class
        for _ in range(num_detections):
            # Ensure there is enough data to process the next detection
            if index + 5 > len(output_array):
                # Break to prevent accessing out-of-bounds indices
                break

            # Extract confidence score and bounding box values
            score = float(output_array[index + 4])
            y_min, x_min, y_max, x_max = map(float, output_array[index : index + 4])
            index += 5  # Move index to the next detection entry

            # Skip detections if the confidence score is below the threshold
            if score < confidence_threshold:
                continue

            # Convert bounding box coordinates to absolute pixel values
            x_min = x_min * input_width
            y_min = y_min * input_height
            x_max = x_max * input_width
            y_max = y_max * input_height

            # Create a detection result with bbox, score, and class label
            result = {
                "bbox": [x_min, y_min, x_max, y_max],  # Bounding box in pixel coordinates
                "score": score,  # Confidence score of the detection
                "category_id": class_id,  # Class ID of the detected object
                "label": label_dictionary.get(str(class_id), f"class_{class_id}"),  # Class label or fallback
            }
            new_inference_results.append(result)  # Store the formatted detection

        # Stop parsing if remaining output is padded with zeros (no more detections)
        if index >= len(output_array) or all(v == 0 for v in output_array[index:]):
            break

    # Return the final list of detection results
    return new_inference_results




def iou( boxA, boxB):
    # função IoU simples
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2]-boxA[0]) * (boxA[3]-boxA[1])
    boxBArea = (boxB[2]-boxB[0]) * (boxB[3]-boxB[1])

    return interArea / float(boxAArea + boxBArea - interArea + 1e-6)

def iou_matrix_np(dets_xyxy, trks_xyxy):
    """
    dets_xyxy: (D,4)
    trks_xyxy: (T,4)
    return: (T,D) IoU
    """
    if dets_xyxy.size == 0 or trks_xyxy.size == 0:
        return np.zeros((trks_xyxy.shape[0], dets_xyxy.shape[0]), dtype=np.float32)

    # Expand dims p/ broadcast
    d = dets_xyxy[None, :, :]   # (1,D,4)
    t = trks_xyxy[:, None, :]   # (T,1,4)

    xx1 = np.maximum(t[..., 0], d[..., 0])
    yy1 = np.maximum(t[..., 1], d[..., 1])
    xx2 = np.minimum(t[..., 2], d[..., 2])
    yy2 = np.minimum(t[..., 3], d[..., 3])

    w = np.maximum(0.0, xx2 - xx1)
    h = np.maximum(0.0, yy2 - yy1)
    inter = w * h

    area_t = (t[..., 2] - t[..., 0]) * (t[..., 3] - t[..., 1])
    area_d = (d[..., 2] - d[..., 0]) * (d[..., 3] - d[..., 1])

    return inter / (area_t + area_d - inter + 1e-6)



class IDManager:
    def __init__(self):
        # id FIXO  último bbox
        self.fixed_last_bbox = {}
        # IOU para associar Sort e BBOX
        self.iou_assign_threshold = 0.2

        # Objetos com IDs fixas
        self.fixed_ids = {
            "ram" :2,
            "hand" :2,
            "cpu": 1,
            "motherboard": 1,
            "fan":1,
            "pallet":1}
        
        self.fixed_objects = {}
        self.last_fixed_objects = {}
        self.miss_counter = {}          # fixed_id -> frames sem atualização
        self.max_miss_frames = 3        # ajuste (2~5 é bom)
        for cls, count in self.fixed_ids.items():
            for i in range(1, count+1):
                fid = f"{cls}{i}"
                self.fixed_objects[fid] = {"class": cls, "bbox": None, "track_id": None, "active": False}
                self.miss_counter[fid] = 0

        # dict do sort associado a IDs fixos 
        self.sort_to_fixed = {}

        self.unassigned_cache = {}  # track_id -> dict
        self.UNASSIGNED_MIN_HITS = 3
        self.UNASSIGNED_MAX_MISS = 4
        self.UNASSIGNED_ALPHA = 0.4

        self.trackers_by_class = {
            "hand": Sort(max_age=50, min_hits=1, iou_threshold=0.15),
            "ram":  Sort(max_age=50, min_hits=1, iou_threshold=0.2),
            "cpu":  Sort(max_age=100, min_hits=1, iou_threshold=0.2),
            "motherboard": Sort(max_age=50, min_hits=1, iou_threshold=0.2),
            "fan":  Sort(max_age=50, min_hits=1, iou_threshold=0.2),
            "pallet": Sort(max_age=50, min_hits=1, iou_threshold=0.2),

        }

        self.topk = {"hand":2, "ram":4, "cpu":3, "motherboard":3, "fan":3, "pallet":3}

        self.tracks = []  # guarda tracks do frame (para cleanup)

    def _free_fixed_id(self, fixed_id: str):
        """Libera um fixed_id e remove qualquer sort_id que esteja mapeado nele."""
        # remove sort_id -> fixed_id
        for sid, fid in list(self.sort_to_fixed.items()):
            if fid == fixed_id:
                del self.sort_to_fixed[sid]

        obj = self.fixed_objects[fixed_id]
        obj["active"] = False
        obj["bbox"] = None
        obj["track_id"] = None
        obj["source"] = None if "source" in obj else obj.get("source")
        self.miss_counter[fixed_id] = 0

    def _build_sort_input(self, dets_cls, k):
        # dets_cls: lista de dets já da classe
        if not dets_cls:
            return np.empty((0,5), dtype=np.float32)

        # top-k por score
        dets_cls = sorted(dets_cls, key=lambda d: d["score"], reverse=True)[:k]
        arr = np.array([[*d["bbox"], d["score"]] for d in dets_cls], dtype=np.float32)
        return arr

    def assign_tracks_all_classes(self, detections):
        by_cls = defaultdict(list)
        for det in detections:
            lbl = det["label"]
            if lbl in self.trackers_by_class:
                by_cls[lbl].append(det)

        all_tracks = []  # saída unificada: track_id,bbox,label
        self.tracks = [] # para cleanup: lista de track_ids ativos globais

        for cls, tracker in self.trackers_by_class.items():
            sort_in = self._build_sort_input(by_cls.get(cls, []), self.topk.get(cls, 1))
            trks = tracker.update(sort_in)  # [[x1,y1,x2,y2,id],...]

            for t in trks:
                x1,y1,x2,y2,tid = t
                tid = int(tid)

                # ⚠️ IDs repetem entre classes, então faça um ID global barato:
                # combine classe + tid em uma string (ou hash int)
                global_id = f"{cls}:{tid}"

                all_tracks.append({"track_id": global_id, "bbox":[float(x1),float(y1),float(x2),float(y2)], "label": cls})
                self.tracks.append(global_id)

        return all_tracks

    def check_available_ids_from_tracks(self, labels_with_id):
        # NÃO roda SORT aqui. Só usa a lista labels_with_id.
        self.last_fixed_objects = copy.deepcopy(self.fixed_objects)

        for fid in self.fixed_objects:
            self.fixed_objects[fid]["active"] = False

        for item in labels_with_id:
            sort_id = item["track_id"]   # ex: "ram:3"
            bbox    = item["bbox"]
            label   = item["label"]

            if label is None:
                continue

            if sort_id in self.sort_to_fixed:
                fixed_id = self.sort_to_fixed[sort_id]
            else:
                fixed_id = self._assign_new_fixed_id(label)
                if fixed_id is None:
                    continue
                self.sort_to_fixed[sort_id] = fixed_id

            obj = self.fixed_objects[fixed_id]
            obj["bbox"] = bbox
            obj["track_id"] = sort_id
            obj["active"] = True

        self._cleanup_dead_tracks()
        return self.fixed_objects




        
    def _cleanup_dead_tracks(self):
        active_sort_ids = set(self.tracks)
        for sort_id in list(self.sort_to_fixed.keys()):
            if sort_id not in active_sort_ids:
                fixed_id = self.sort_to_fixed[sort_id]
                obj = self.fixed_objects[fixed_id]
                obj["active"] = False
                obj["track_id"] = None
                obj["bbox"] = None
                del self.sort_to_fixed[sort_id]



    def check_available_ids(self, detections):
        # não use deepcopy todo frame (custa). Se precisar, deixe, mas não é essencial.
        # self.last_fixed_objects = copy.deepcopy(self.fixed_objects)

        # marca todo mundo como "não atualizado neste frame"
        updated_fixed = set()

        labels_with_id = self.assign_tracks_all_classes(detections)

        for item in labels_with_id:
            sort_id = item["track_id"]
            bbox = item["bbox"]
            label = item["label"]
            if label is None:
                continue

            # reutiliza mapping
            if sort_id in self.sort_to_fixed:
                fixed_id = self.sort_to_fixed[sort_id]
            else:
                fixed_id = self._assign_new_fixed_id(label)
                if fixed_id is None:
                    continue
                self.sort_to_fixed[sort_id] = fixed_id

            obj = self.fixed_objects[fixed_id]
            obj["bbox"] = bbox
            obj["track_id"] = sort_id
            obj["active"] = True

            self.miss_counter[fixed_id] = 0         # ✅ reset miss
            updated_fixed.add(fixed_id)

        # ✅ histerese: quem não foi atualizado, incrementa miss
        for fid, obj in self.fixed_objects.items():
            if fid not in updated_fixed:
                self.miss_counter[fid] += 1
                if self.miss_counter[fid] >= self.max_miss_frames:
                    self._free_fixed_id(fid)

            else:
                obj["active"] = True  # mantém ativo

        # ❗️NÃO remova sort_to_fixed agressivamente aqui.
        # Deixe o miss_counter decidir quando matar.
        # self._cleanup_dead_tracks()  # <- comente/remova

        return self.fixed_objects

        
    def _assign_new_fixed_id(self, label):
        """
        Retorna um fixed_id livre para a classe.
        Se não houver, retorna None.
        """

        for fid, obj in self.fixed_objects.items():
            # só IDs da classe correta
            if obj["class"] != label:
                continue

            # ID livre = nunca associado ou não está ativo
            if not obj["active"] and fid not in self.sort_to_fixed.values():
                return fid

        # Nenhum ID disponível para a classe
        return None
    

    def predict_only(self):
        updated_fixed = set()

        for cls, tracker in self.trackers_by_class.items():
            tracker.update(np.empty((0, 5), dtype=np.float32))  # advance kalman

            for trk in tracker.trackers:
                tid = int(trk.id + 1)            # ID compatível com Sort.update()
                sort_id = f"{cls}:{tid}"

                if sort_id not in self.sort_to_fixed:
                    continue

                fixed_id = self.sort_to_fixed[sort_id]

                d = trk.get_state()[0]
                bbox = [float(d[0]), float(d[1]), float(d[2]), float(d[3])]

                obj = self.fixed_objects[fixed_id]
                obj["bbox"] = bbox
                obj["track_id"] = sort_id
                obj["active"] = True

                self.miss_counter[fixed_id] = 0
                updated_fixed.add(fixed_id)

        # histerese para os que não foram atualizados
        for fid, obj in self.fixed_objects.items():
            if fid not in updated_fixed:
                self.miss_counter[fid] += 1
                if self.miss_counter[fid] >= self.max_miss_frames:
                    self._free_fixed_id(fid)

        return self.fixed_objects


    def get_unassigned_tracks(self, all_tracks, fixed_objects):
        """
        all_tracks: lista de dicts -> [{"track_id": "ram:3", "bbox":[...], "label":"ram"}, ...]
        fixed_objects: dict -> {"ram1": {"track_id":"ram:3", ...}, ...}

        Retorna tracks que NÃO foram associados a nenhum fixed_id.
        """
        used_track_ids = {
            obj["track_id"]
            for obj in fixed_objects.values()
            if obj.get("track_id") is not None
        }

        unassigned = []
        for t in all_tracks:
            tid = t.get("track_id")
            if tid is None:
                continue
            if tid not in used_track_ids:
                unassigned.append({
                    "track_id": tid,
                    "bbox": t.get("bbox"),
                    "label": t.get("label")
                })

        return unassigned
    






