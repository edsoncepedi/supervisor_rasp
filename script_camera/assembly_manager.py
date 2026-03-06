from hailo_postprocess import iou

import math

from collections import Counter
  

class AssemblyManagar:
    def __init__(self, posto:int):
        self.etapa_atual= int(1)
        self.posto = posto # 0, '1 ou 2
        self.frame = None
        self.valid2 = False
        self.valid3 = False
        #self.etapas_posto1 = {"1":["hand", "cpu"], "2":["cpu", "motherboard"], "3":["hand", "fan"], "4":["fan", "motheboard"]}
        #self.etapas_posto2 = {"1":["hand", "ram"], "2":["hand", "motherboard"], "3":["hand", "ram"], "4":["hand", "motherboard"]}

        self.iou_threshold = {
            "hand_ram": 0.02,
            "hand_cpu": 0.05,
            "fan_hand": 0.03,
            "mb_cpu": 0.03,
            "mb_fan": 0.1
        }

        self._iou_cache = {}

    def contar_produtos_posto(self, detections):
        contagem = Counter(d["label"] for d in detections)
        #print(contagem) 


    def _has_measurement(self, detections):
        return any(v["active"] for v in detections.values())
    
    def update(self, detections: dict):
        """
        detections = fixed_objects
        """
        self._build_iou_cache(detections)

    # só usa objetos medidos
        if not self._has_measurement(detections):
            return self.etapa_atual

        return self._run_fsm(detections)

    def _run_fsm(self, d):
        match self.etapa_atual:
            case 1:
                if self._etapa1(d):
                    self.etapa_atual += 1
            case 2:
                if self._etapa2(d):
                    self.etapa_atual += 1
            case 3:
                if self._etapa3(d):
                    self.etapa_atual += 1
            case 4:
                if self._etapa4(d):
                    self.etapa_atual += 1

        return self.etapa_atual

    def _verificar_boxes_validas(self, detections, fid):
        if detections[fid]["bbox"] is not None:
            return True
        else:
            return False
    
    def _build_iou_cache(self, detections):
        self._iou_cache.clear()

        keys = [k for k, v in detections.items() if v["active"] and v["bbox"]]

        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                self._iou_cache[(a, b)] = iou(detections[a]["bbox"],
                                            detections[b]["bbox"])


    def _iou(self, a, b):
        return self._iou_cache.get((a, b), self._iou_cache.get((b, a), 0.0))

    def _etapa1(self, d) -> bool:
        if self.posto == 1:
            return (self._iou("hand1", "cpu1") > self.iou_threshold["hand_cpu"] or
                    self._iou("hand2", "cpu1") > self.iou_threshold["hand_cpu"])

        elif self.posto == 2:
            thr = self.iou_threshold["hand_ram"]
            return (self._iou("hand1", "ram1") > thr or
                    self._iou("hand1", "ram2") > thr or
                    self._iou("hand2", "ram1") > thr or
                    self._iou("hand2", "ram2") > thr)

        return False

    def _etapa2(self, d) -> bool:
        if self.posto == 1:
            iou_mb_cpu = self._iou("motherboard1", "cpu1")
            iou_mb_h1  = self._iou("motherboard1", "hand1")
            iou_mb_h2  = self._iou("motherboard1", "hand2")
            return (iou_mb_cpu > self.iou_threshold["mb_cpu"] and iou_mb_h1 == 0.0 and iou_mb_h2 == 0.0)

        elif self.posto == 2:
            iouA = self._iou("motherboard1", "hand1")
            iouB = self._iou("motherboard1", "hand2")

            if not self.valid2:
       
                if (d["ram1"]["active"] and iouA > 0.1  and not d["ram2"]["active"]):
                    self.valid2 = True
                    return False
                if (d["ram1"]["active"] and iouB > 0.1 and not d["ram2"]["active"]):
                    self.valid2 = True
                    return False
                if (d["ram2"]["active"] and iouA > 0.1 and not d["ram1"]["active"]):
                    self.valid2 = True
                    return False
                if (d["ram2"]["active"] and iouB > 0.1 and not d["ram1"]["active"]):
                    self.valid2 = True
                    return False


            else:
                if iouA == 0.0 and iouB == 0.0:
                    self.valid2 = False
                    return True
        return False


    def _etapa3(self, d) -> bool:
        if self.posto == 1:
            thr = self.iou_threshold["fan_hand"]
            return (self._iou("fan1", "hand1") > thr or self._iou("fan1", "hand2") > thr)

        elif self.posto == 2:
            # mantém seu reset de etapa
            if d["ram1"]["active"] and d["ram2"]["active"]:
                self.etapa_atual = 2
                return False

            thr = self.iou_threshold["hand_ram"]
            return (self._iou("hand1", "ram1") > thr or
                    self._iou("hand1", "ram2") > thr or
                    self._iou("hand2", "ram1") > thr or
                    self._iou("hand2", "ram2") > thr)

        return False


    def _etapa4(self, d) -> bool:
        if self.posto == 1:
            iou_mb_fan = self._iou("motherboard1", "fan1")
            iou_mb_h1  = self._iou("motherboard1", "hand1")
            iou_mb_h2  = self._iou("motherboard1", "hand2")
            return (iou_mb_fan > self.iou_threshold["mb_fan"] and iou_mb_h1 == 0.0 and iou_mb_h2 == 0.0)

        elif self.posto == 2:
            if d["ram1"]["active"] and d["ram2"]["active"]:
                self.etapa_atual = 3
                return False

            iouA = self._iou("motherboard1", "hand1")
            iouB = self._iou("motherboard1", "hand2")

            if not self.valid3:
                if (not d["ram1"]["active"] and iouA > 0.1  and not d["ram2"]["active"]):
                    self.valid3 = True
                    return False
                if (not d["ram1"]["active"] and iouB > 0.1 and not d["ram2"]["active"]):
                    self.valid3 = True
                    return False
            else:
                if iouA == 0.0 and iouB == 0.0:
                    self.valid3 = False
                    return True

        return False



def bbox_inside_roi(bbox, roi, min_overlap=0.1):
    x1, y1, x2, y2 = bbox
    rx1, ry1, rx2, ry2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]

    # Interseção
    ix1 = max(x1, rx1)
    iy1 = max(y1, ry1)
    ix2 = min(x2, rx2)
    iy2 = min(y2, ry2)

    if ix2 <= ix1 or iy2 <= iy1:
        return False

    inter_area = (ix2 - ix1) * (iy2 - iy1)
    bbox_area = (x2 - x1) * (y2 - y1)

    return (inter_area / bbox_area) >= min_overlap
