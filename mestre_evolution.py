import time
import os
import json
import requests 
import re
import gc
import psutil 
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
# Keys ainda é útil para limpar campos, mesmo clicando no botão depois
from selenium.webdriver.common.keys import Keys 
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager

# ==============================================================================
# ⚙️ 1. CONFIGURAÇÕES GERAIS
# ==============================================================================

# --- URLS ---
URL_DASHBOARD = "https://paineladmin3.azurewebsites.net/mobfy/dashboard"
URL_LOGIN = "https://paineladmin3.azurewebsites.net/mobfy/login" # URL base para logar
URL_MAPA = "https://paineladmin3.azurewebsites.net/mobfy/vermapa"

# --- CREDENCIAIS (Variáveis de Ambiente do EasyPanel) ---
# Configure "PAINEL_USER" e "PAINEL_PASS" no EasyPanel. 
# Os valores abaixo são apenas fallback para teste local.
USUARIO_PAINEL = os.getenv("PAINEL_USER", "admin@teste.com") 
SENHA_PAINEL = os.getenv("PAINEL_PASS", "123456")

# --- EVOLUTION API ---
EVOLUTION_URL = "https://n8n-evolution-teste.laalxr.easypanel.host/"      
EVOLUTION_INSTANCE = "Evoteste"        
EVOLUTION_APIKEY = "2026-01-14T11:55:42.000Z"           

# --- 👥 CONTATOS (IDs) ---
MAPA_CONTATOS = {
    "GRUPO_AVISOS": "554991777170@s.whatsapp.net",
    "DONO": "553899003357@s.whatsapp.net",
    "MATHEUS": "554989000629@s.whatsapp.net",
    "NEIVA": "554989032654@s.whatsapp.net",
    "JOAO": "554991777170@s.whatsapp.net"
}

NOME_GRUPO_AVISOS = "GRUPO_AVISOS"
LISTA_RELATORIOS = ["DONO", "MATHEUS", "NEIVA", "GRUPO_AVISOS"]
ADMINS_TECNICOS = ["DONO", "JOAO"]

# --- PARÂMETROS DO ROBÔ ---
TICKET_MEDIO = 15.00
TEMPO_OFFLINE = 3       
TEMPO_FROTA = 15        
TEMPO_CORRIDAS = 30     
TEMPO_HEARTBEAT = 40   
PORCENTAGEM_CRITICA_OCUPACAO = 60   
TEMPO_COOLDOWN_REFORCO = 30         
QTD_CRITICA_OFFLINE = 16            

# --- ARQUIVOS LOCAIS ---
diretorio_base = os.path.dirname(os.path.abspath(__file__))
CAMINHO_PERFIL_PAINEL = os.path.join(diretorio_base, "sessao_firefox_painel")
ARQUIVO_DADOS = os.path.join(diretorio_base, "dados_dia.json")

# --- ESTADO ---
hora_inicio_bot = time.time()
ultimo_aviso_reforco = 0
estatisticas_dia = {'data': time.strftime('%Y-%m-%d'), 'pico': 0, 'hora_pico': "", 'fechamento_enviado': False}

# ==============================================================================
# 🔐 2. FUNÇÃO DE LOGIN (ATUALIZADA)
# ==============================================================================
def fazer_login_automatico(driver):
    print("🔑 Iniciando processo de login...")
    try:
        # Se já estiver logado, sai da função
        if "dashboard" in driver.current_url and "login" not in driver.current_url:
            print("✅ Sessão anterior ativa. Login pulado.")
            return

        driver.get(URL_LOGIN)
        time.sleep(5) # Espera carregar o site

        # 1. Preencher Usuário
        try:
            xpath_user = "/html/body/div/app/body/div/div[2]/form/div[1]/input"
            campo_user = driver.find_element(By.XPATH, xpath_user)
            campo_user.clear()
            campo_user.send_keys(USUARIO_PAINEL)
            print("👤 Usuário preenchido.")
        except Exception as e:
            print(f"❌ Erro campo Usuário: {e}")
            return

        # 2. Preencher Senha
        try:
            xpath_pass = "/html/body/div/app/body/div/div[2]/form/div[2]/input"
            campo_senha = driver.find_element(By.XPATH, xpath_pass)
            campo_senha.clear()
            campo_senha.send_keys(SENHA_PAINEL)
            print("🔑 Senha preenchida.")
        except Exception as e:
            print(f"❌ Erro campo Senha: {e}")
            return
        
        time.sleep(1) 

        # 3. Clicar no Botão de Entrar (NOVO)
        try:
            xpath_btn = "/html/body/div/app/body/div/div[2]/form/div[4]/input"
            botao = driver.find_element(By.XPATH, xpath_btn)
            botao.click()
            print("🖱️ Botão 'Entrar' clicado.")
        except Exception as e:
            print(f"❌ Erro ao clicar no botão: {e}")
            # Tentativa de emergência com Enter se o clique falhar
            campo_senha.send_keys(Keys.ENTER) 
        
        print("⏳ Aguardando acesso...")
        time.sleep(10)
        
        if "dashboard" in driver.current_url:
            print("✅ LOGIN REALIZADO COM SUCESSO!")
        else:
            print(f"⚠️ Alerta: URL atual ainda é {driver.current_url}. Verifique credenciais.")

    except Exception as e:
        print(f"❌ Falha crítica no login: {e}")

# ==============================================================================
# 💾 3. PERSISTÊNCIA E MENSAGENS
# ==============================================================================
def carregar_dados():
    global estatisticas_dia
    if os.path.exists(ARQUIVO_DADOS):
        try:
            with open(ARQUIVO_DADOS, 'r') as f:
                dados = json.load(f)
                if dados.get('data') == time.strftime('%Y-%m-%d'):
                    estatisticas_dia = dados
        except: pass

def salvar_dados():
    try:
        estatisticas_dia['data'] = time.strftime('%Y-%m-%d')
        with open(ARQUIVO_DADOS, 'w') as f:
            json.dump(estatisticas_dia, f)
    except: pass

carregar_dados()

def enviar_mensagem_evolution(mensagem, destinatarios):
    if not isinstance(destinatarios, list): destinatarios = [destinatarios]
    
    for target_key in destinatarios:
        # Pega o ID e remove espaços em branco extras
        numero = MAPA_CONTATOS.get(target_key, target_key).strip()
        
        print(f"📤 [API] Tentando enviar para {target_key} ({numero})...")
        
        url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        headers = {
            "apikey": EVOLUTION_APIKEY,
            "Content-Type": "application/json"
        }
        
        # 🔧 FIX PARA GRUPOS:
        # Se tiver "@g.us", algumas versões preferem que não use o campo 'number' puramente
        # ou requerem o campo remoteJid explícito. Vamos enviar de forma híbrida.
        payload = {
            "number": numero,  # Mantemos para compatibilidade
            "options": {
                "delay": 1200,
                "presence": "composing",
                "linkPreview": False
            },
            "textMessage": {
                "text": mensagem
            }
        }

        # Se for um grupo, forçamos o remoteJid no nível raiz (algumas versões exigem isso)
        # Nota: O endpoint /sendText aceita payload simplificado, mas o completo é mais seguro para grupos
        if "@g.us" in numero:
             # Sobrescreve payload para formato mais específico se falhar o simples
             payload = {
                "number": numero, 
                "text": mensagem,
                "delay": 1200,
                "linkPreview": False
             }
             
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            
            # --- ÁREA DE DIAGNÓSTICO MELHORADA ---
            if response.status_code in [200, 201]:
                data = response.json()
                # Verifica se a API retornou erro lógico mesmo com status 200
                if 'key' in data or 'message' in data:
                    print(f"✅ [SUCESSO] Mensagem enviada para {target_key}")
                else:
                    print(f"⚠️ [ALERTA] API retornou 200 mas resposta estranha: {data}")
            else:
                print(f"❌ [ERRO API] Status: {response.status_code}")
                print(f"📝 [BODY] {response.text}")
            # ---------------------------

        except Exception as e:
            print(f"❌ [ERRO CONEXÃO] O Python não conseguiu chamar a API: {e}")
            
        time.sleep(1)

# ==============================================================================
# 🛠️ 4. FERRAMENTAS DO SISTEMA
# ==============================================================================
def criar_driver_painel():
    print(f"🦊 Iniciando Firefox...")
    options = FirefoxOptions()
    if not os.path.exists(CAMINHO_PERFIL_PAINEL): os.makedirs(CAMINHO_PERFIL_PAINEL)
    options.add_argument("-profile"); options.add_argument(CAMINHO_PERFIL_PAINEL)
    options.add_argument("--headless") # Roda sem interface gráfica (ideal para VPS)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    servico = Service(GeckoDriverManager().install())
    return webdriver.Firefox(service=servico, options=options)

def ler_texto(driver, xpath):
    try:
        el = driver.find_element(By.XPATH, xpath)
        return el.text if el.text else el.get_attribute("textContent")
    except: return "0"

def obter_uso_vps():
    try:
        cpu_uso = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        ram_uso_gb = mem.used / (1024 ** 3)
        ram_total_gb = mem.total / (1024 ** 3)
        return cpu_uso, mem.percent, f"{ram_uso_gb:.1f}GB/{ram_total_gb:.1f}GB"
    except: return 0, 0, "?/?"

def filtrar_dados_offline(texto_bruto):
    if not texto_bruto: return "🚫 Dados Carregando..."
    try:
        # Busca por "Nome:" seguido de qualquer texto até o fim da linha
        match_nome = re.search(r'Nome:\s*(.+)', texto_bruto)
        nome = match_nome.group(1).strip() if match_nome else "Motorista"
        
        # Busca por "Celular:" (ignorando maiúsculas/minúsculas) e pega números/traços
        match_cel = re.search(r'Celular:\s*([0-9\(\)\-\s]+)', texto_bruto, re.IGNORECASE)
        telefone = match_cel.group(1).strip() if match_cel else "Sem nº"

        return f"🚫 {nome} \n📞 {telefone}"
    except: return f"🚫 Erro Leitura"

# ==============================================================================
# 🧩 5. TAREFAS DE MONITORAMENTO
# ==============================================================================
def tarefa_offline(driver_painel):
    """
    Lê do PAINEL via Selenium, manda no ZAP via Evolution API.
    """
    print("\n🔍 [OFFLINE] Buscando pinos amarelos...")
    
    try:
        # --- 1. Navegação no Painel ---
        if URL_MAPA not in driver_painel.current_url:
            driver_painel.get(URL_MAPA)
            time.sleep(5)
        else:
            driver_painel.refresh()
            time.sleep(10)

        # Busca os elementos
        amarelos = driver_painel.find_elements(By.CSS_SELECTOR, "img[src*='pin-amarelo.png']")
        qtd_offline = len(amarelos)
        
        if qtd_offline == 0:
            print("✅ [OFFLINE] Rede estável.")
            return

        # --- 2. Caso Crítico ---
        if qtd_offline >= QTD_CRITICA_OFFLINE:
            print(f"⚠️ [CRÍTICO] {qtd_offline} offlines!")
            mensagem = (
                f"⚠️ *AVISO DE INSTABILIDADE DE REDE*\n\n"
                f"O sistema detectou **{qtd_offline} motoristas offline** simultaneamente.\n"
                f"Possível falha na operadora de telefonia. Recomendamos reiniciar os aparelhos."
            )
            enviar_mensagem_evolution(mensagem, NOME_GRUPO_AVISOS)
            return

        # --- 3. Leitura Individual ---
        print(f"⚠️ [OFFLINE] {qtd_offline} detectados. Lendo...")
        lista_final = []

        # Limita a 15 para não travar
        for pino in amarelos[:15]: 
            try:
                driver_painel.execute_script("arguments[0].click();", pino)
                time.sleep(1.5)
                
                try:
                    balao = driver_painel.find_element(By.CLASS_NAME, "gm-style-iw")
                    # Usa a função auxiliar criada
                    lista_final.append(f"🔸 {filtrar_dados_offline(balao.text)}")
                except: 
                    lista_final.append("🚫 Erro ao ler balão")
                
                try: driver_painel.find_element(By.CLASS_NAME, "gm-ui-hover-effect").click()
                except: driver_painel.find_element(By.TAG_NAME, 'body').click()
                time.sleep(0.5)
            except: 
                continue

        # --- 4. Envio do Relatório ---
        if lista_final:
            texto_zap = "\n".join(lista_final)
            mensagem = (
                f"⚠️ *ALERTA: MOTORISTAS OFFLINE - {time.strftime('%H:%M')}*\n"
                f"📡 Total Sem Sinal: {qtd_offline}\n\n"
                f"{texto_zap}"
            )
            enviar_mensagem_evolution(mensagem, NOME_GRUPO_AVISOS)

    except Exception as e:
        print(f"❌ Erro Tarefa Offline: {e}")

def tarefa_frota(driver):
    global ultimo_aviso_reforco
    print("\n🚗 [FROTA] Verificando...")
    try:
        if URL_MAPA not in driver.current_url: driver.get(URL_MAPA); time.sleep(6)
        livres = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='verde']"))
        ocupados = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='vermelho']")) + \
                   len(driver.find_elements(By.CSS_SELECTOR, "img[src*='ocupado']"))
        total = livres + ocupados
        if total > estatisticas_dia['pico']:
            estatisticas_dia['pico'] = total; estatisticas_dia['hora_pico'] = time.strftime('%H:%M'); salvar_dados()
        
        if total > 0:
            porc = round((ocupados / total) * 100)
            status = "🟢" if porc <= 40 else "🟡" if porc <= 75 else "🔴 ALTA"
            msg_stats = (
            f"📊 *STATUS DA FROTA | {time.strftime('%H:%M')}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status} - {porc}% de ocupação\n\n"
            f"🟢 Disponíveis: {livres}\n"
            f"🔴 Em Atendimento: {ocupados}\n"
            f"🚗 Total Logado: {total}\n"
            f"━━━━━━━━━━━━━━━━━━"
            )
            enviar_mensagem_evolution(msg_stats, "GRUPO_AVISOS")
            
            agora = time.time()
            if (porc >= PORCENTAGEM_CRITICA_OCUPACAO) and ((agora - ultimo_aviso_reforco)/60 >= TEMPO_COOLDOWN_REFORCO):
                enviar_mensagem_evolution(f"⚠️ *REFORÇO:* Demanda alta ({porc}%).", "GRUPO_AVISOS")
                ultimo_aviso_reforco = agora
    except: pass

def tarefa_dashboard(driver, enviar=True):
    print("\n📈 [DASHBOARD] Lendo...")
    try:
        driver.get(URL_DASHBOARD); time.sleep(8)
        xp_sol = '/html/body/div/app/div/div/div[2]/div[2]/div/div[1]/h3'
        xp_con = '/html/body/div/app/div/div/div[2]/div[3]/div/div[1]/h3'
        try:
            txt_sol = ler_texto(driver, xp_sol); txt_con = ler_texto(driver, xp_con)
            sol = int(txt_sol.replace('.','')); con = int(txt_con.replace('.',''))
            perdidas = sol - con
            conversao = round((con / sol) * 100) if sol > 0 else 0
        except: sol, con, perdidas = 0, 0, 0
        
        if enviar:
            msg = (
                f"📈 *Relatório de Desempenho - {time.strftime('%H:%M')}*\n"
                f"📥 Solicitações: {txt_sol}\n"
                f"✅ Finalizadas: {txt_con}\n"
                f"🚫 Não Atendidas: {perdidas}\n"
                f"📊 Taxa de Conversão: {conversao}%"
            )
            enviar_mensagem_evolution(msg, LISTA_RELATORIOS)
        return sol, con, perdidas
    except: return 0, 0, 0

def tarefa_heartbeat():
    uptime = round((time.time() - hora_inicio_bot) / 3600, 1)
    cpu, ram_porc, ram_info = obter_uso_vps()
    icone = "🟢" if ram_porc < 85 else "⚠️"
    msg = (f"🤖 *Monitor* {icone}\n⏱️ Up: {uptime}h\n🧠 CPU: {cpu}%\n💾 RAM: {ram_porc}% ({ram_info})")
    enviar_mensagem_evolution(msg, ADMINS_TECNICOS)

def tarefa_fechamento_dia(driver):
    s, c, p = tarefa_dashboard(driver, enviar=False)
    fat = c * TICKET_MEDIO
    msg = (f"🌙 *FECHAMENTO {time.strftime('%d/%m')}*\n✅ Corridas: {c}\n🚫 Perdidas: {p}\n💰 Fat.: R$ {fat:,.2f}")
    enviar_mensagem_evolution(msg, "DONO")
    estatisticas_dia['pico'] = 0; estatisticas_dia['fechamento_enviado'] = True; salvar_dados()

def tarefa_reiniciar_bot(driver, motivo):
    """Fecha o navegador e mata o processo. O EasyPanel reinicia sozinho."""
    print(f"🔄 [RESTART] Reiniciando: {motivo}")
    try:
        msg = f"♻️ *REINÍCIO AUTOMÁTICO (3h)*\n\nMotivo: {motivo}\nVoltaremos em alguns segundos..."
        enviar_mensagem_evolution(msg, ADMINS_TECNICOS)
        driver.quit()
    except: pass
    
    time.sleep(2)
    sys.exit(0) # Isso encerra o Python e o Docker reinicia ele limpo

# ==============================================================================
# 🔄 6. LOOP PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Iniciando MESTRE (Automático via Evolution)...")
    
    # 1. Cria o navegador
    driver = criar_driver_painel()
    
    # 2. Faz o Login Automático
    fazer_login_automatico(driver)
    
    agora = time.time()
    t_off = agora + 10     # Começa em 10s
    t_frota = agora + 20   # Começa em 20s
    t_dash = agora + 60    # Começa em 60s
    t_heart = agora + 5    # Manda sinal de vida logo
    t_restart = agora + (3 * 60 * 60)

    enviar_mensagem_evolution("🚀 *Sistema Iniciado e Logado.*", ADMINS_TECNICOS)

    while True:
        try:
            agora = time.time()
            
            # --- TAREFAS ---
            if agora >= t_off: 
                tarefa_offline(driver)
                t_off = agora + (TEMPO_OFFLINE * 60)
            
            if agora >= t_frota: 
                tarefa_frota(driver)
                t_frota = agora + (TEMPO_FROTA * 60)
            
            if agora >= t_dash: 
                tarefa_dashboard(driver)
                t_dash = agora + (TEMPO_CORRIDAS * 60)
            
            if agora >= t_heart:
                tarefa_heartbeat()
                t_heart = agora + (TEMPO_HEARTBEAT * 60)
                gc.collect() # Limpa memória RAM
            if agora >= t_restart:
                # Passamos o 'driver' para ele poder fechar o navegador antes de sair
                tarefa_reiniciar_bot(driver, "Manutenção programada")

            # --- FECHAMENTO (23:59) ---
            hora = time.localtime()
            if hora.tm_hour == 23 and hora.tm_min >= 58 and not estatisticas_dia['fechamento_enviado']:
                tarefa_fechamento_dia(driver)
            
            # Reseta flag meia-noite
            if hora.tm_hour == 0 and hora.tm_min == 1:
                estatisticas_dia['fechamento_enviado'] = False

            time.sleep(10) # Delay para economizar CPU

        except KeyboardInterrupt:
            driver.quit(); break
        except Exception as e:
            print(f"⚠️ Erro Global Loop: {e}"); time.sleep(15)
