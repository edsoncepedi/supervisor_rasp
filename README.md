Guia Rápido — Comandos do Supervisor
=========================================

O Supervisor é um gerenciador de processos no Linux.  
Com ele, é possível iniciar, parar e monitorar scripts Python (ou qualquer outro programa) facilmente.

⚙️ Gerenciar Programas
----------------------
sudo supervisorctl start <nome>        # Inicia um programa específico
sudo supervisorctl stop <nome>         # Para um programa
sudo supervisorctl restart <nome>      # Reinicia um programa
sudo supervisorctl status              # Mostra status de todos os programas
sudo supervisorctl tail <nome>         # Mostra o final do log (stdout)
sudo supervisorctl tail -f <nome>      # Segue o log em tempo real

🔄 Atualizar Configurações
--------------------------
sudo supervisorctl reread              # Lê novamente os arquivos .conf
sudo supervisorctl update              # Aplica mudanças (start/stop conforme necessário)
sudo supervisorctl reload              # Reinicia o processo supervisord inteiro

🧰 Controlar o Serviço Supervisor (systemd)
-------------------------------------------
sudo systemctl status supervisor       # Mostra o status do serviço Supervisor
sudo systemctl restart supervisor      # Reinicia o Supervisor inteiro
sudo systemctl enable supervisor       # Faz o Supervisor iniciar no boot
sudo systemctl disable supervisor      # Impede que ele inicie no boot

📁 Estrutura e Arquivos Importantes
-----------------------------------
/etc/supervisor/supervisord.conf       # Arquivo principal (geral, raramente editado)
/etc/supervisor/conf.d/                # Onde ficam os .conf de cada app
/var/log/                              # Onde ficam os logs (.out.log e .err.log)

🔍 Dicas Rápidas
----------------
# Visualizar logs
tail -f /var/log/script_comando.out.log
tail -f /var/log/script_comando.err.log

# Recarregar todas as configurações
sudo supervisorctl reread && sudo supervisorctl update

# Parar tudo
sudo supervisorctl stop all

# Iniciar tudo
sudo supervisorctl start all

✅ Resumo Rápido (Top 10 Comandos)
----------------------------------
sudo supervisorctl status              # Ver status de todos os programas
sudo supervisorctl start nome          # Inicia um programa
sudo supervisorctl stop nome           # Para um programa
sudo supervisorctl restart nome        # Reinicia um programa
sudo supervisorctl reread              # Recarrega configs dos .conf
sudo supervisorctl update              # Aplica novas configs detectadas
sudo supervisorctl tail -f nome        # Ver log em tempo real
sudo supervisorctl reload              # Reinicia o Supervisor inteiro
sudo systemctl status supervisor       # Ver status do serviço Supervisor
sudo systemctl enable supervisor       # Habilita no boot

💡 Dica: mantenha cada aplicação em um arquivo .conf separado dentro de /etc/supervisor/conf.d/
e use 'reread + update' sempre que editar algo.
