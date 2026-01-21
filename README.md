# 📘 Guia Rápido — Comandos do Supervisor

O **Supervisor** é um gerenciador de processos no Linux.  
Com ele, é possível iniciar, parar e monitorar scripts Python (ou qualquer outro programa) facilmente.

---

## ⚙️ Gerenciar Programas

| Comando | Função | Exemplo |
|----------|--------|----------|
| `sudo supervisorctl start <nome>` | Inicia um programa específico | `sudo supervisorctl start script_comando` |
| `sudo supervisorctl stop <nome>` | Para um programa | `sudo supervisorctl stop script_comando` |
| `sudo supervisorctl restart <nome>` | Reinicia o programa | `sudo supervisorctl restart script_comando` |
| `sudo supervisorctl status` | Mostra status de todos os programas | `sudo supervisorctl status` |
| `sudo supervisorctl tail <nome>` | Mostra o final do log (`stdout`) do programa | `sudo supervisorctl tail script_comando` |
| `sudo supervisorctl tail -f <nome>` | Segue o log em tempo real (como `docker logs -f`) | `sudo supervisorctl tail -f script_comando` |

---

## 🔄 Atualizar Configurações

| Comando | Função | Quando usar |
|----------|--------|--------------|
| `sudo supervisorctl reread` | Lê novamente os arquivos `.conf` | Após editar ou criar um `.conf` novo |
| `sudo supervisorctl update` | Aplica mudanças (start/stop conforme necessário) | Sempre após o `reread` |
| `sudo supervisorctl reload` | Reinicia o processo **supervisord** inteiro | Quando mexe em algo global (raro) |

---

## 🧰 Controlar o Serviço Supervisor (systemd)

| Comando | Função |
|----------|--------|
| `sudo systemctl status supervisor` | Mostra o status do serviço Supervisor |
| `sudo systemctl restart supervisor` | Reinicia o Supervisor inteiro |
| `sudo systemctl enable supervisor` | Faz o Supervisor iniciar no boot |
| `sudo systemctl disable supervisor` | Impede que ele inicie no boot |

---

## 📁 Estrutura e Arquivos Importantes

| Caminho | Função |
|----------|--------|
| `/etc/supervisor/supervisord.conf` | Arquivo principal (geral, raramente editado) |
| `/etc/supervisor/conf.d/` | Onde ficam os `.conf` de cada app |
| `/var/log/` | Onde ficam os logs (`.out.log` e `.err.log`) |

---

## 🔍 Dicas Rápidas

### Visualizar logs
```bash
tail -f /var/log/script_comando.out.log
tail -f /var/log/script_comando.err.log
```

### Recarregar todas as configurações
```bash
sudo supervisorctl reread && sudo supervisorctl update
```

### Parar tudo
```bash
sudo supervisorctl stop all
```

### Iniciar tudo
```bash
sudo supervisorctl start all
```

---

## ✅ Resumo Rápido (Top 10 Comandos)

| Comando | Descrição |
|----------|------------|
| `sudo supervisorctl status` | Ver status de todos os programas |
| `sudo supervisorctl start nome` | Inicia um programa |
| `sudo supervisorctl stop nome` | Para um programa |
| `sudo supervisorctl restart nome` | Reinicia um programa |
| `sudo supervisorctl reread` | Recarrega configurações dos `.conf` |
| `sudo supervisorctl update` | Aplica novas configs detectadas |
| `sudo supervisorctl tail -f nome` | Ver log em tempo real |
| `sudo supervisorctl reload` | Reinicia o Supervisor inteiro |
| `sudo systemctl status supervisor` | Ver status do serviço Supervisor |
| `sudo systemctl enable supervisor` | Habilita no boot |

---

> 💡 **Dica:** mantenha cada aplicação em um `.conf` separado dentro de `/etc/supervisor/conf.d/`,  
> e use `reread + update` sempre que editar algo.


## ⚙️ Requisitos do Sistema

Para garantir a compatibilidade total com este projeto, é necessário utilizar a versão específica do **Raspberry Pi OS** listada abaixo.

> **⚠️ Atenção:** Não utilize a versão padrão mais recente (que utiliza Wayland). O projeto foi homologado para funcionar na versão **Legacy** (baseada em X11).

### Versão Homologada:
* **Nome:** `Raspberry Pi OS (Legacy, 64-bit) Full`
* **Base:** Port of Debian Bookworm
* **Data de Lançamento:** 2025-11-24
* **Tamanho:** ~3.2 GB

Certifique-se de escolher a opção que inclui **"Desktop environment and recommended applications"**.
