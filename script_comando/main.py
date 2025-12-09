import requests
import RPi.GPIO as GPIO
import time
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

def button_calback(channel):
    print("Botão Pressionado")
    # Defina a URL e os dados a serem enviados na requisição POST
    url = f"http://{os.getenv('IP_SERVER')}/comando"
    payload = {'comando': 'imprime_produto'}

    # Cabeçalhos da requisição
    headers = {'Content-Type': 'application/json'}

    # Envia o POST
    response = requests.post(url, json=payload, headers=headers)

    # Imprima o código de status e o conteúdo da resposta
    print(f"Código de Status: {response.status_code}")
    print(f"Conteúdo da Resposta: {response.text}")

def main():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(11, GPIO.IN) 
    
    GPIO.add_event_detect(11, GPIO.FALLING, callback=button_calback, bouncetime=1000)

    try:
        while True:
            time.sleep(1)
    except:
        GPIO.cleanup()
            

if __name__ == "__main__":
    main()
