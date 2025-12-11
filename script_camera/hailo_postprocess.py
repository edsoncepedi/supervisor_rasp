import numpy as np
from sort import Sort


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







class IDManager:
    def __init__(self):
        # id FIXO → último bbox
        self.fixed_last_bbox = {}

        # id SORT → id 
        self.sort_to_fixed = {}

        # nomes referentes
        self.labels = {
            0: "cpu",
            1: "fan1",
            2: "motherboard",
            3: "pallet",
            4: "ram1",
            5: "ram2",
            6: "hand1",
            7: "hand2"
        }

    def iou(self, boxA, boxB):
        # função IoU simples
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = (boxA[2]-boxA[0]) * (boxA[3]-boxA[1])
        boxBArea = (boxB[2]-boxB[0]) * (boxB[3]-boxB[1])

        return interArea / float(boxAArea + boxBArea - interArea + 1e-6)

        

        
    def assign(self, track_id, bbox, class_id):
        """
        track_id   = ID criado pelo SORT
        bbox       = caixa atual rastreada
        class_id   = classificação YOLO 
        """

        # 1. Caso o objeto tenha classe única — atribuição direta
        if class_id in self.fixed_last_bbox:
            self.sort_to_fixed[track_id] = class_id
            self.fixed_last_bbox[class_id] = bbox
            return class_id

        # 2. Se é novo (class ID ainda não apareceu)
        # então simplesmente associamos
        self.fixed_last_bbox[class_id] = bbox
        self.sort_to_fixed[track_id] = class_id
        return class_id

    def get_fixed_id(self, sort_id):
        return self.sort_to_fixed.get(sort_id, None)

    def get_label(self, fixed_id):
        return self.labels.get(fixed_id, "unknown")
