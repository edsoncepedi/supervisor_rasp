import numpy as np
from sort import Sort
import re
import copy

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

        for obj_class, count in self.fixed_ids.items():
            for i in range(1, count + 1):
                fid = f"{obj_class}{i}"

                self.fixed_objects[fid] = {
                    "class": obj_class,
                    "bbox": None,
                    "track_id": None,
                    "active": False
                }

        # dict do sort associado a IDs fixos 
        self.sort_to_fixed = {}

        self.tracker = Sort(
            max_age=200,
            min_hits=3,
            iou_threshold=0.3
        )       
        
    def assign_id_to_label(self, detections):

        sort_input = []

        # Preparar entrada do SORT
        for det in detections:
            x1, y1, x2, y2 = map(float, det["bbox"])
            score = float(det["score"])
            sort_input.append([x1, y1, x2, y2, score])

        sort_input = np.array(sort_input) if len(sort_input) > 0 else np.empty((0, 5))

        # Atualizar SORT
        self.tracks = self.tracker.update(sort_input)

        sort_with_label = []

        # Associar track ↔ label via IOU
        for track in self.tracks:
            tx1, ty1, tx2, ty2, track_id = track
            track_bbox = [tx1, ty1, tx2, ty2]

            best_iou = 0.0
            best_label = None

            for det in detections:
                det_bbox = det["bbox"]
                i = iou(det_bbox, track_bbox)

                if i > best_iou:
                    best_iou = i
                    best_label = det["label"]

            # Aceita associação ou mantém track sem label

            sort_with_label.append({
                "track_id": int(track_id),
                "bbox": track_bbox,
                "label": best_label if best_iou >= self.iou_assign_threshold else None
            })
                    


        return sort_with_label
    def get_unassigned_tracks(self, detections, fixed_ids):
        unassigned = []
        fixed_track_ids = {
            slot["track_id"]
            for slot in fixed_ids.values()
            if slot.get("track_id") is not None
        }

        for item in detections:
            track_id = item['track_id']
            x1, y1, x2, y2 = item['bbox']
            label = item['label']

            if track_id not in fixed_track_ids:
                unassigned.append({
                    "track_id": track_id,
                    "bbox": [x1, y1, x2, y2],
                    "label": label
                })

        return unassigned



        
    def _cleanup_dead_tracks(self):
        active_sort_ids = {int(track[-1]) for track in self.tracks}

        for sort_id in list(self.sort_to_fixed.keys()):
            if sort_id not in active_sort_ids:
                fixed_id = self.sort_to_fixed[sort_id]

                # libera o ID
                self.fixed_objects[fixed_id]["active"] = False
                self.fixed_objects[fixed_id]["track_id"] = None
                self.fixed_objects[fixed_id]["bbox"] = None

                del self.sort_to_fixed[sort_id]


    def check_available_ids(self, detections):

        self.last_fixed_objects = copy.deepcopy(self.fixed_objects)

        for fid in self.fixed_objects:
            self.fixed_objects[fid]["active"] = False

        labels_with_id = self.assign_id_to_label(detections)

        for item in labels_with_id:
            sort_id = item["track_id"]
            bbox = item["bbox"]
            label = item["label"]

            if label is None:
                continue

            # SORT já tinha fixed_id  reutiliza
            if sort_id in self.sort_to_fixed:
                fixed_id = self.sort_to_fixed[sort_id]

            else:
                # 2SORT novo  tenta pegar ID livre
                fixed_id = self._assign_new_fixed_id(label)

                if fixed_id is None:
                    
                    #print(f" Classe '{label}' sem IDs disponíveis")
                    continue

                self.sort_to_fixed[sort_id] = fixed_id

            # Atualiza estado
            obj = self.fixed_objects[fixed_id]
            obj["bbox"] = bbox
            obj["track_id"] = sort_id
            obj["active"] = True

        self._cleanup_dead_tracks()
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

