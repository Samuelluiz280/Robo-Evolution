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
EVOLUTION_APIKEY = "DEV280@NEXT"           

# --- 👥 CONTATOS (IDs) ---
MAPA_CONTATOS = {
    "GRUPO_AVISOS": "120363421503531873@g.us",
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
    print("🔑 Iniciando login (Modo: Persistente)...")
    try:
        # Se já estiver logado, sai
        if "dashboard" in driver.current_url and "login" not in driver.current_url:
            print("✅ Sessão anterior ativa.")
            return

        driver.get(URL_LOGIN)
        
        # --- LOOP DE ESPERA (30 SEGUNDOS) ---
        # Sites em Angular/React demoram para "desenhar" os inputs na tela.
        # Vamos tentar encontrar os inputs 6 vezes, esperando 5s cada vez.
        todos_inputs = []
        for tentativa in range(1, 7):
            print(f"⏳ Tentativa {tentativa}/6 de encontrar formulário...")
            time.sleep(5)
            todos_inputs = driver.find_elements(By.TAG_NAME, "input")
            if len(todos_inputs) > 0:
                print(f"✅ Formulário carregado! Encontrados {len(todos_inputs)} campos.")
                break
        
        # Se depois de 30s ainda for 0, imprime o erro
        if len(todos_inputs) == 0:
            print("❌ ERRO: A página carregou mas está SEM CAMPOS (Tela Branca/Loading).")
            print(f"TITULO DA PAGINA: {driver.title}")
            try:
                # Imprime um pedaço do HTML para sabermos se é erro do servidor
                html_body = driver.find_element(By.TAG_NAME, "body").get_attribute("innerHTML")
                print(f"🔎 CONTEÚDO DA TELA: {html_body[:300]}...") 
            except: pass
            return

        # --- ESTRATÉGIA: PEGAR PELO ÍNDICE (Mantida, pois é boa) ---
        campo_user = None
        campo_senha = None

        # 1. Acha Senha
        try: campo_senha = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        except: 
            if len(todos_inputs) >= 2: campo_senha = todos_inputs[1]

        # 2. Acha Usuário (Primeiro input que não é senha/hidden)
        candidatos_user = [
            i for i in todos_inputs
            if i.get_attribute("type") not in ['password', 'hidden', 'checkbox', 'radio', 'submit', 'button']
        ]

        if len(candidatos_user) > 0: campo_user = candidatos_user[0]

        if campo_user and campo_senha:
            try:
                campo_user.clear(); campo_user.send_keys(USUARIO_PAINEL)
                print("👤 Usuário preenchido.")
                time.sleep(0.5)
                campo_senha.clear(); campo_senha.send_keys(SENHA_PAINEL)
                print("🔑 Senha preenchida.")
                time.sleep(1)
                campo_senha.send_keys(Keys.ENTER)
                print("🖱️ Enter enviado.")
            except Exception as e:
                print(f"❌ Erro ao digitar: {e}")
        else:
            print("❌ Falha: Inputs existem mas não identifiquei usuário/senha.")

        print("⏳ Aguardando redirecionamento...")
        time.sleep(15)
        
        if "dashboard" in driver.current_url:
            print("✅ LOGIN REALIZADO COM SUCESSO!")

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
        # Pega o ID e garante que não tem espaços
        numero = MAPA_CONTATOS.get(target_key, target_key).strip()
        
        print(f"📤 [API] Tentando enviar para {target_key} ({numero})...")
        
        # URL Correta (sem barra no final nas configs globais)
        url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        
        headers = {
            "apikey": EVOLUTION_APIKEY,
            "Content-Type": "application/json"
        }
        
        # --- CORREÇÃO AQUI ---
        # Usamos a estrutura COMPLETA para todos (Grupos e Contatos)
        # Isso evita o Erro 400 por JSON mal formatado
        payload = {
            "number": numero,
            "options": {
                "delay": 1200,
                "presence": "composing",
                "linkPreview": False
            },
            "textMessage": {
                "text": mensagem
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            
            if response.status_code in [200, 201]:
                print(f"✅ [SUCESSO] Mensagem enviada para {target_key}")
            else:
                # Aqui veremos o detalhe do erro 400 se persistir
                print(f"❌ [ERRO API] Status: {response.status_code}")
                print(f"📝 [RESPOSTA] {response.text}")

        except Exception as e:
            print(f"❌ [ERRO CONEXÃO] {e}")
            
        time.sleep(1)
        
# ==============================================================================
# 🛠️ 4. FERRAMENTAS DO SISTEMA
# ==============================================================================
def criar_driver_painel():
    print(f"🦊 Iniciando Firefox (Modo Full HD)...")
    options = FirefoxOptions()
    if not os.path.exists(CAMINHO_PERFIL_PAINEL): os.makedirs(CAMINHO_PERFIL_PAINEL)
    options.add_argument("-profile"); options.add_argument(CAMINHO_PERFIL_PAINEL)
    options.add_argument("--headless") 
    
    # --- NOVO: Configurações para evitar tela branca ---
    options.add_argument("--window-size=1920,1080") # Tela grande
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    # Finge ser um navegador comum para evitar bloqueios
    options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
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
    print("\n🚗 [FROTA] Iniciando navegação...")
    
    try:
        # --- 1. VERIFICAÇÃO DE SEGURANÇA (Login/Sessão) ---
        # Se estiver na tela de login, reinicia para limpar memória (Estratégia Nuclear)
        if len(driver.find_elements(By.CSS_SELECTOR, "img[src*='logoLogin']")) > 0:
            print("⚠️ Sessão caiu (Logo detectada). Reiniciando container...")
            driver.quit(); sys.exit(0)

        # --- 2. NAVEGAÇÃO HUMANA (CLICAR NO BOTÃO) ---
        # Se NÃO estamos no mapa, precisamos ir pra lá clicando
        if "vermapa" not in driver.current_url:
            print("🔄 Indo para o Dashboard para achar o botão...")
            if "dashboard" not in driver.current_url:
                driver.get(URL_DASHBOARD)
                time.sleep(8)
            
            print("🔎 Procurando botão 'Ver Mapa'...")
            try:
                # Tenta clicar pelo texto do link (Método mais preciso)
                botao_mapa = driver.find_element(By.PARTIAL_LINK_TEXT, "Ver Mapa")
                botao_mapa.click()
                print("🖱️ CLIQUEI no botão 'Ver Mapa'!")
                time.sleep(15) # Espera o mapa carregar
            except:
                print("⚠️ Botão não achado pelo texto. Tentando forçar URL...")
                driver.get(URL_MAPA) # Último recurso
                time.sleep(15)
        
        # --- 3. CONTAGEM DOS CARROS ---
        print("👀 Contando veículos na tela...")
        
        # Busca imagens de carros (Verde = Livre, Vermelho/Ocupado = Ocupado)
        livres = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='verde']"))
        ocupados = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='vermelho']")) + \
                   len(driver.find_elements(By.CSS_SELECTOR, "img[src*='ocupado']"))
        
        # PLANO B: Se a contagem der 0 (ícones mudaram de nome?), conta genéricos
        if livres == 0 and ocupados == 0:
             # Pega todas as imagens PNG
             todas_imgs = driver.find_elements(By.CSS_SELECTOR, "img[src*='.png']")
             # Remove o que sabemos que NÃO é carro (logo, avatar, etc)
             potenciais_carros = [
                 img for img in todas_imgs 
                 if "logo" not in img.get_attribute("src") 
                 and "purple" not in img.get_attribute("src")
                 and "user" not in img.get_attribute("src")
             ]
             
             if len(potenciais_carros) > 0:
                 print(f"⚠️ Ícones padrão não achados. Usando {len(potenciais_carros)} ícones genéricos.")
                 # Chute conservador: divide meio a meio se não souber a cor
                 ocupados = len(potenciais_carros) 
             
        total = livres + ocupados
        print(f"🔢 Contagem Final: Livres={livres} | Ocupados={ocupados} | Total={total}")
        
        # --- 4. RELATÓRIOS E ENVIO ---
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
            # Envia para o grupo
            enviar_mensagem_evolution(msg_stats, "GRUPO_AVISOS")
            
            # Lógica de Reforço (Alerta de Alta Demanda)
            agora = time.time()
            if (porc >= PORCENTAGEM_CRITICA_OCUPACAO) and ((agora - ultimo_aviso_reforco)/60 >= TEMPO_COOLDOWN_REFORCO):
                enviar_mensagem_evolution(f"⚠️ *REFORÇO:* Demanda alta ({porc}%).", "GRUPO_AVISOS")
                ultimo_aviso_reforco = agora
                
    except SystemExit: raise # Respeita o reinício nuclear
    except Exception as e:
        print(f"❌ Erro Frota: {e}")
        
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
