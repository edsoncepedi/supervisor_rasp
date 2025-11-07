import requests

# URL do endpoint Flask
url = "http://172.16.10.175:7000/rfid__checkin_posto"  # altere IP/porta conforme seu Flask

# Tag RFID (simulada aqui, mas poderia vir de um leitor)
tag = "584197450694"
posto = "posto_0"

# Corpo da requisição (JSON)
payload = {'tag': tag, 'posto': posto}
headers = {'Content-Type': 'application/json'}

try:
    # Envia o POST para o servidor Flask
    response = requests.post(url, json=payload, headers=headers)

    # Exibe o resultado
    print(f"Código de Status: {response.status_code}")
    print(f"Resposta: {response.text}")

    # Opcional: interpretar o JSON de retorno
    if response.ok:
        data = response.json()
        if data.get("autorizado"):
            print(f"Acesso liberado para: {data['funcionario']['nome']}")
            # Aqui você pode acionar um relé, LED, buzzer, etc.
        else:
            print("Acesso negado ou tag não reconhecida.")
    else:
        print("Erro na comunicação com o servidor.")

except Exception as e:
    print(f"Erro ao enviar requisição: {e}")