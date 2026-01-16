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
from selenium.webdriver.common.keys import Keys 
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager

# ==============================================================================
# ⚙️ 1. CONFIGURAÇÕES GERAIS
# ==============================================================================

# --- URLS ---
URL_DASHBOARD = "https://paineladmin3.azurewebsites.net/mobfy/dashboard"
URL_LOGIN = "https://paineladmin3.azurewebsites.net/mobfy/login" 
URL_MAPA = "https://paineladmin3.azurewebsites.net/mobfy/vermapa"

# --- CREDENCIAIS ---
USUARIO_PAINEL = os.getenv("PAINEL_USER", "admin@teste.com") 
SENHA_PAINEL = os.getenv("PAINEL_PASS", "123456")

# --- EVOLUTION API ---
EVOLUTION_URL = "https://n8n-evolution-teste.laalxr.easypanel.host"
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
# 🔐 2. FUNÇÃO DE LOGIN E PREPARAÇÃO DE ABAS
# ==============================================================================
def fazer_login_automatico(driver):
    print("🔑 Iniciando login (Modo: Persistente)...")
    try:
        if "dashboard" in driver.current_url and "login" not in driver.current_url:
            print("✅ Sessão anterior ativa.")
            return

        driver.get(URL_LOGIN)
        
        # Loop de espera para o formulário aparecer
        todos_inputs = []
        for tentativa in range(1, 7):
            print(f"⏳ Tentativa {tentativa}/6 de encontrar formulário...")
            time.sleep(5)
            todos_inputs = driver.find_elements(By.TAG_NAME, "input")
            if len(todos_inputs) > 0:
                print(f"✅ Formulário carregado! Encontrados {len(todos_inputs)} campos.")
                break
        
        if len(todos_inputs) == 0:
            print("❌ ERRO: Tela branca ou loading eterno.")
            return

        # Estratégia de preenchimento
        campo_user = None
        campo_senha = None

        try: campo_senha = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        except: 
            if len(todos_inputs) >= 2: campo_senha = todos_inputs[1]

        candidatos_user = [i for i in todos_inputs if i.get_attribute("type") not in ['password', 'hidden', 'submit']]
        if len(candidatos_user) > 0: campo_user = candidatos_user[0]

        if campo_user and campo_senha:
            try:
                campo_user.clear(); campo_user.send_keys(USUARIO_PAINEL)
                time.sleep(0.5)
                campo_senha.clear(); campo_senha.send_keys(SENHA_PAINEL)
                time.sleep(1)
                campo_senha.send_keys(Keys.ENTER)
                print("🖱️ Credenciais enviadas.")
            except Exception as e:
                print(f"❌ Erro ao digitar: {e}")
        
        print("⏳ Aguardando redirecionamento...")
        time.sleep(15)
        
        if "dashboard" in driver.current_url:
            print("✅ LOGIN REALIZADO COM SUCESSO!")

    except Exception as e:
        print(f"❌ Falha crítica no login: {e}")

def preparar_abas(driver):
    """
    Configura o ambiente de DUAS ABAS:
    - Aba 0: Dashboard (Mantém sessão viva)
    - Aba 1: Mapa (Fica aberta direto para leitura rápida)
    """
    print("📑 Configurando sistema de ABAS...")
    try:
        # Garante que estamos na Aba 0 (Dashboard)
        driver.switch_to.window(driver.window_handles[0])
        if "dashboard" not in driver.current_url:
            driver.get(URL_DASHBOARD)
            time.sleep(5)

        # Abre Aba 1 (Mapa) se não existir
        if len(driver.window_handles) < 2:
            print("➕ Abrindo nova aba para o Mapa...")
            driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(2)
        
        # Vai para a Aba 1 e carrega o mapa via CLIQUE (Segurança)
        driver.switch_to.window(driver.window_handles[1])
        print("🗺️ Carregando Mapa na Aba 2...")
        
        driver.get(URL_DASHBOARD) # Entra no dashboard na aba 2
        time.sleep(5)
        
        try:
            print("🔎 Clicando no botão 'Ver Mapa' na Aba 2...")
            driver.find_element(By.PARTIAL_LINK_TEXT, "Ver Mapa").click()
            time.sleep(10)
        except:
            print("⚠️ Clique falhou na Aba 2, tentando URL direta...")
            driver.get(URL_MAPA)
            time.sleep(10)
        
        # Volta o foco para a Aba 0 para começar o ciclo
        driver.switch_to.window(driver.window_handles[0])
        print("✅ Sistema de abas pronto!")
        
    except Exception as e:
        print(f"❌ Erro ao preparar abas: {e}")

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
        numero = MAPA_CONTATOS.get(target_key, target_key).strip()
        print(f"📤 [API] Enviando para {target_key}...")
        
        url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
        
        payload = {
            "number": numero,
            "options": {"delay": 1200, "presence": "composing", "linkPreview": False},
            "textMessage": {"text": mensagem}
        }

        try:
            requests.post(url, json=payload, headers=headers, timeout=10)
        except: pass
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
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--width=1920"); options.add_argument("--height=1080")
    options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage")
    servico = Service(GeckoDriverManager().install())
    return webdriver.Firefox(service=servico, options=options)

def ler_texto(driver, xpath):
    try:
        el = driver.find_element(By.XPATH, xpath)
        return el.text if el.text else el.get_attribute("textContent")
    except: return "0"

def obter_uso_vps():
    try:
        mem = psutil.virtual_memory()
        return psutil.cpu_percent(interval=1), mem.percent, f"{mem.used/(1024**3):.1f}GB"
    except: return 0, 0, "?"

def filtrar_dados_offline(texto_bruto):
    if not texto_bruto: return "🚫 Dados Carregando..."
    try:
        match_nome = re.search(r'Nome:\s*(.+)', texto_bruto)
        nome = match_nome.group(1).strip() if match_nome else "Motorista"
        match_cel = re.search(r'Celular:\s*([0-9\(\)\-\s]+)', texto_bruto, re.IGNORECASE)
        telefone = match_cel.group(1).strip() if match_cel else "Sem nº"
        return f"🚫 {nome} \n📞 {telefone}"
    except: return f"🚫 Erro Leitura"

# ==============================================================================
# 🧩 5. TAREFAS (COM SUPORTE A DUAS ABAS)
# ==============================================================================

def verificar_sessao_e_trocar_aba(driver, indice_aba):
    """
    Garante que estamos na aba certa e logados.
    """
    try:
        driver.switch_to.window(driver.window_handles[indice_aba])
        
        # Verifica queda de sessão (Logo + Senha)
        tem_logo = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='logoLogin']")) > 0
        tem_senha = len(driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) > 0
        
        if tem_logo and tem_senha:
            print("🔥 SESSÃO CAIU! Reiniciando container para limpar tudo...")
            driver.quit(); sys.exit(0)
            
        return True
    except IndexError:
        print("⚠️ Aba fechada inesperadamente. Reiniciando...")
        driver.quit(); sys.exit(0)
    except Exception:
        return False

def tarefa_dashboard(driver, enviar=True):
    print("\n📈 [DASHBOARD - ABA 1] Lendo...")
    # Muda para ABA 0 (Dashboard)
    verificar_sessao_e_trocar_aba(driver, 0)
    
    try:
        # Recarrega para manter sessão viva (Heartbeat)
        driver.refresh()
        time.sleep(5)
        
        try:
            xp_sol = '/html/body/div/app/div/div/div[2]/div[2]/div/div[1]/h3'
            xp_con = '/html/body/div/app/div/div/div[2]/div[3]/div/div[1]/h3'
            txt_sol = ler_texto(driver, xp_sol); txt_con = ler_texto(driver, xp_con)
            sol = int(txt_sol.replace('.','')); con = int(txt_con.replace('.',''))
            perdidas = sol - con
            conversao = round((con / sol) * 100) if sol > 0 else 0
        except: sol, con, perdidas = 0, 0, 0
        
        if enviar:
            msg = (
                f"📈 *Relatório - {time.strftime('%H:%M')}*\n"
                f"📥 Solicitações: {txt_sol}\n✅ Finalizadas: {txt_con}\n"
                f"🚫 Perdidas: {perdidas}\n📊 Conversão: {conversao}%"
            )
            enviar_mensagem_evolution(msg, LISTA_RELATORIOS)
        return sol, con, perdidas
    except: return 0, 0, 0

def tarefa_frota(driver):
    global ultimo_aviso_reforco
    print("\n🚗 [FROTA - ABA 2] Verificando...")
    verificar_sessao_e_trocar_aba(driver, 1)

    try:
        # 1. DIAGNÓSTICO RÁPIDO: Onde estamos?
        # Se o título não tiver "Mapa" ou "MobFy", pode estar na tela errada
        print(f"📍 Título da Página: {driver.title}")

        if "vermapa" not in driver.current_url:
            print("🔄 URL incorreta na Aba 2. Tentando recarregar via Dashboard...")
            driver.get(URL_DASHBOARD); time.sleep(5)
            try: driver.find_element(By.PARTIAL_LINK_TEXT, "Ver Mapa").click()
            except: driver.get(URL_MAPA)
            time.sleep(15)

        # 2. TENTATIVA DE ENTRAR EM IFRAME (Muito comum em Google Maps)
        # Se houver um iframe, o robô mergulha nele para procurar os carros
        if len(driver.find_elements(By.TAG_NAME, "iframe")) > 0:
            print("🖼️ Iframe detectado! Tentando entrar no mapa...")
            try:
                # Tenta achar o iframe do mapa (geralmente o maior ou primeiro)
                iframe = driver.find_elements(By.TAG_NAME, "iframe")[0]
                driver.switch_to.frame(iframe)
            except: pass

        # 3. CONTAGEM TURBINADA (Imagens + Divs + Clusters)
        print("👀 Escaneando mapa...")
        
        # A. Busca Clássica (Imagens PNG)
        livres = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='verde'], img[src*='green'], img[src*='free']"))
        ocupados = len(driver.find_elements(By.CSS_SELECTOR, "img[src*='vermelho'], img[src*='red'], img[src*='ocupado']"))
        
        # B. Busca por DIVs (Marcadores modernos do Google Maps)
        # Muitas vezes o carro é uma DIV com role='button' ou background-image
        if livres == 0 and ocupados == 0:
            # Procura elementos que parecem botões no mapa (pinos)
            pinos_div = driver.find_elements(By.CSS_SELECTOR, "div[role='button']")
            # Filtra os que são muito pequenos ou controles de zoom
            pinos_validos = [p for p in pinos_div if p.size['width'] > 20 and "Zoom" not in p.get_attribute("title")]
            
            if len(pinos_validos) > 0:
                print(f"⚠️ Achei {len(pinos_validos)} pinos do tipo DIV. Usando contagem mista.")
                # Como não sabemos a cor da DIV, jogamos tudo em ocupados para alertar (ou divide 50%)
                ocupados = len(pinos_validos)

        # C. Busca por CLUSTERS (Bolinhas com números)
        # Se o mapa estiver muito longe, ele agrupa os carros.
        # Procuramos divs que contenham apenas números (ex: "15", "5")
        if livres == 0 and ocupados == 0:
            clusters = driver.find_elements(By.CSS_SELECTOR, "div")
            total_cluster = 0
            for c in clusters:
                # Se o texto for um número pequeno (ex: '5') e o elemento for pequeno (cluster)
                if c.text.isdigit() and len(c.text) <= 3 and c.size['width'] < 60 and c.size['width'] > 20:
                    try: total_cluster += int(c.text)
                    except: pass
            
            if total_cluster > 0:
                print(f"⚠️ Mapa Agrupado (Cluster)! Detectei aprox. {total_cluster} veículos.")
                ocupados = total_cluster # Assume total

        # Sai do iframe se entrou
        driver.switch_to.default_content()

        total = livres + ocupados
        print(f"🔢 Frota Detectada: {total} (L:{livres}/O:{ocupados})")
        
        # --- LÓGICA DE ENVIO (IGUAL AO ANTERIOR) ---
        if total > estatisticas_dia['pico']:
            estatisticas_dia['pico'] = total; estatisticas_dia['hora_pico'] = time.strftime('%H:%M'); salvar_dados()
        
        if total > 0:
            porc = round((ocupados / total) * 100)
            status = "🟢" if porc <= 40 else "🟡" if porc <= 75 else "🔴 ALTA"
            msg = (
            f"📊 *STATUS FROTA | {time.strftime('%H:%M')}*\n"
            f"{status} - {porc}% ocupado\n🟢 Livres: {livres}\n🔴 Ocupados: {ocupados}\n🚗 Total: {total}"
            )
            enviar_mensagem_evolution(msg, NOME_GRUPO_AVISOS)
            
            agora = time.time()
            if (porc >= PORCENTAGEM_CRITICA_OCUPACAO) and ((agora - ultimo_aviso_reforco)/60 >= TEMPO_COOLDOWN_REFORCO):
                enviar_mensagem_evolution(f"⚠️ *REFORÇO:* Demanda alta ({porc}%).", NOME_GRUPO_AVISOS)
                ultimo_aviso_reforco = agora

    except SystemExit: raise
    except Exception as e: print(f"❌ Erro Frota: {e}")

    except SystemExit: raise
    except Exception as e: print(f"❌ Erro Frota: {e}")

def tarefa_offline(driver):
    print("\n🔍 [OFFLINE - ABA 2] Buscando...")
    # Muda para ABA 1 (Mapa)
    verificar_sessao_e_trocar_aba(driver, 1)
    
    try:
        amarelos = driver.find_elements(By.CSS_SELECTOR, "img[src*='pin-amarelo.png']")
        qtd = len(amarelos)
        
        if qtd >= QTD_CRITICA_OFFLINE:
            msg = f"⚠️ *CRÍTICO:* {qtd} motoristas offline! Verifique a rede."
            enviar_mensagem_evolution(msg, NOME_GRUPO_AVISOS)
            return

        if qtd > 0:
            print(f"⚠️ {qtd} Offlines. Lendo detalhes...")
            lista = []
            for pino in amarelos[:10]:
                try:
                    driver.execute_script("arguments[0].click();", pino); time.sleep(1)
                    txt = driver.find_element(By.CLASS_NAME, "gm-style-iw").text
                    lista.append(f"🔸 {filtrar_dados_offline(txt)}")
                    try: driver.find_element(By.CLASS_NAME, "gm-ui-hover-effect").click()
                    except: pass
                except: continue
            
            if lista:
                msg = f"⚠️ *OFFLINES - {time.strftime('%H:%M')}*\n📡 Total: {qtd}\n\n" + "\n".join(lista)
                enviar_mensagem_evolution(msg, NOME_GRUPO_AVISOS)
        else:
            print("✅ Rede estável.")

    except SystemExit: raise
    except Exception as e: print(f"❌ Erro Offline: {e}")

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
    print(f"🔄 [RESTART] Reiniciando: {motivo}")
    try:
        msg = f"♻️ *REINÍCIO (3h)*\nMotivo: {motivo}"
        enviar_mensagem_evolution(msg, ADMINS_TECNICOS)
        driver.quit()
    except: pass
    time.sleep(2); sys.exit(0)

# ==============================================================================
# 🔄 LOOP
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Iniciando MESTRE (Modo Multi-Abas)...")
    
    driver = criar_driver_painel()
    fazer_login_automatico(driver)
    preparar_abas(driver) # <--- ABRE A SEGUNDA ABA AQUI
    
    agora = time.time()
    t_off = agora + 10; t_frota = agora + 20
    t_dash = agora + 60; t_heart = agora + 5
    t_restart = agora + (3 * 3600)

    enviar_mensagem_evolution("🚀 *Sistema Iniciado (Multi-Abas).*", ADMINS_TECNICOS)

    while True:
        try:
            agora = time.time()
            
            if agora >= t_off: 
                tarefa_offline(driver); t_off = agora + (TEMPO_OFFLINE * 60)
            
            if agora >= t_frota: 
                tarefa_frota(driver); t_frota = agora + (TEMPO_FROTA * 60)
            
            if agora >= t_dash: 
                tarefa_dashboard(driver); t_dash = agora + (TEMPO_CORRIDAS * 60)
            
            if agora >= t_heart:
                tarefa_heartbeat(); t_heart = agora + (TEMPO_HEARTBEAT * 60); gc.collect()

            if agora >= t_restart:
                tarefa_reiniciar_bot(driver, "Manutenção")

            hora = time.localtime()
            if hora.tm_hour == 23 and hora.tm_min >= 58 and not estatisticas_dia['fechamento_enviado']:
                tarefa_fechamento_dia(driver)
            if hora.tm_hour == 0 and hora.tm_min == 1:
                estatisticas_dia['fechamento_enviado'] = False

            time.sleep(10)

        except KeyboardInterrupt: driver.quit(); break
        except Exception as e: print(f"⚠️ Erro Loop: {e}"); time.sleep(15)