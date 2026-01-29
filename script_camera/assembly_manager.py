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
        self.iou_threshold = [0.05]


    def contar_produtos_posto(self, detections):
        contagem = Counter(d["label"] for d in detections)
        #print(contagem) 
    
        
    def gerenciador_etapas(self, detections)->int:
        
        match self.etapa_atual:
            case 1:
                if self._verificar_etapa1(detections):
                    self.etapa_atual+=1
                
            case 2:
                #print("Começa etapa 2")
                if self._verificar_etapa2(detections):
                    self.etapa_atual+=1

            case 3:
                #print("Começa etapa 3")
                if self._verificar_etapa3(detections):
                    self.etapa_atual+=1

            case 4:
                #print("Começa etapa 4")
                if self._verificar_etapa4(detections):
                    self.etapa_atual+=1

            case 5: 
                print("Posto finalizado ")

        return self.etapa_atual

    def _verificar_boxes_validas(self, detections, fid):
        if detections[fid]["bbox"] is not None:
            return True
        else:
            return False
    
    def _calcular_iou(self, detections, ClasseA, ClasseB):
            if self._verificar_boxes_validas(detections, ClasseA) and self._verificar_boxes_validas(detections, ClasseB):
                return iou(detections[ClasseA]["bbox"],detections[ClasseB]["bbox"] )
            else:
                return 0.0
            
    def _verificar_etapa1(self, detections)-> bool:
        if(self.posto == 1):
            iouA = self._calcular_iou(detections, "hand1", "cpu1")
            if(iouA> self.iou_threshold[0]):
                # Realizar algum trigger aqui <----
                return True
            iouB = self._calcular_iou(detections, "hand2", "cpu1")
            if(iouB> self.iou_threshold[0]):
                # Realizar algum trigger <----
                return True
                            
        elif(self.posto == 2):
            iouA = self._calcular_iou(detections, "hand1", "ram1")
            if(iouA> 0.02):
                # Realizar algum trigger  aqui <----
                return True
            iouB = self._calcular_iou(detections, "hand1", "ram2")
            if(iouB> 0.02):
                # Realizar algum trigger  aqui <----
                return True
            iouC = self._calcular_iou(detections, "hand2", "ram1")
            if(iouC> 0.02):
                # Realizar algum trigger  aqui <----
                return True
            iouD = self._calcular_iou(detections, "hand2", "ram2")
            if(iouD> 0.02):
                # Realizar algum trigger  aqui <----
                return True
        else:
            print("Posto invalido")
        return False

    def _verificar_etapa2(self, detections)->bool:
        if(self.posto == 1):
            iouA = self._calcular_iou(detections, "motherboard1", "cpu1")
            iouB = self._calcular_iou(detections, "motherboard1", "hand1")
            iouC = self._calcular_iou(detections, "motherboard1", "hand2")
            if(iouA>0.03 and iouB == 0.0 and iouC == 0.0):
                return True
            
        elif(self.posto == 2):
            ## Parte 1
            iouA = self._calcular_iou(detections, "motherboard1", "hand1")
            iouB = self._calcular_iou(detections, "motherboard1", "hand2")
            if(not self.valid2):
                if (detections["ram1"]["active"] and iouA>0.1 and iouB>0.1 and not detections["ram2"]["active"]):
                    self.valid2 = True

                if (detections["ram2"]["active"] and iouA>0.1 and iouB>0. and not detections["ram1"]["active"]):
                    self.valid2 = True
            
            if(self.valid2):
            ## Parte 2
                if (detections["ram1"]["active"] and iouA==0 and iouB==0 and not detections["ram2"]["active"]):
                    self.valid2 = False
                    return True
                if (detections["ram2"]["active"] and iouA==0 and iouB==0 and not detections["ram1"]["active"]):
                    self.valid2 = False
                    return True
    
        else:
            print("Posto invalido")
        return False

    def _verificar_etapa3(self, detections):
        if(self.posto == 1):
            iouA = self._calcular_iou(detections, "fan1", "hand1")
            print(iouA)
            if(iouA> 0.3):
                #print("Mão 1 segurando CPU")
                # Realizar algum trigger  agui <----
                return True
            
            iouB = self._calcular_iou(detections, "fan1", "hand2")
            print(iouB)
            if(iouB> 0.3):
                #print("Mão 1 segurando CPU")
                # Realizar algum trigger  agui <----
                return True
        elif(self.posto == 2):
            if (detections["ram1"]["active"] and detections["ram2"]["active"]):
                    self.etapa_atual =2
            iouA = self._calcular_iou(detections, "hand1", "ram1")
            if(iouA> 0.02):
                # Realizar algum trigger  agui <----
                return True
            iouB = self._calcular_iou(detections, "hand1", "ram2")
            if(iouB> 0.02):
                # Realizar algum trigger  agui <----
                return True
            iouC = self._calcular_iou(detections, "hand2", "ram1")
            if(iouC> 0.02):
                # Realizar algum trigger  agui <----
                return True
            iouD = self._calcular_iou(detections, "hand2", "ram2")
            if(iouD> 0.02):
                # Realizar algum trigger  agui <----
                return True
        else:
            print("Posto invalido")
        return False

    def _verificar_etapa4(self, detections):
        if(self.posto == 1):
            iouA = self._calcular_iou(detections, "motherboard1", "fan1")
            iouB = self._calcular_iou(detections, "motherboard1", "hand1")
            iouC = self._calcular_iou(detections, "motherboard1", "hand2")        
            print(iouA)

            if(iouA>0.1 and iouB == 0.0 and iouC == 0.0):
                return True
            else:
                return False
            
        elif(self.posto == 2):

            if (detections["ram1"]["active"] and detections["ram2"]["active"]):
                self.etapa_atual = 2
                return False
            
            ## Parte 1
            iouA = self._calcular_iou(detections, "motherboard1", "hand1")
            iouB = self._calcular_iou(detections, "motherboard1", "hand2")
            if(not self.valid3):
                if (not detections["ram1"]["active"] and iouA>0.1 and iouB>0.1 and not detections["ram2"]["active"]):
                    self.valid3 = True

            
            if(self.valid3):
            ## Parte 2
                if (not detections["ram1"]["active"] and iouA==0 and iouB==0 and not detections["ram2"]["active"]):
                    self.valid3 = False
                    return True
            
        else:
            print("Posto invalido")
        return False


def bbox_inside_roi(bbox, roi, min_overlap=0.3):
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
