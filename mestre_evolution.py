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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

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

def tarefa_monitorar_frota(driver):
    global ultimo_aviso_reforco, estatisticas_dia
    print("\n🚗 [FROTA - ABA 1] Aguardando carregamento do mapa...")
    
    try:
        # 1. Garante Aba e URL
        if not verificar_sessao_e_trocar_aba(driver, 1): return
        
        if "vermapa" not in driver.current_url:
            driver.get(URL_MAPA); time.sleep(10)

        # 2. DETECTOR DE "BLAZOR" (Espera a tela branca sumir)
        # O Blazor geralmente mostra "Loading..." antes de abrir. Vamos esperar passar.
        try:
            # Espera até achar o container principal do mapa ou o menu lateral
            WebDriverWait(driver, 40).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".gm-style, .wrapper, .content-wrapper"))
            )
        except:
            print("⚠️ Alerta: O site demorou muito para responder (Blazor Loading).")

        # 3. DETECTOR DE IFRAME (Caso o mapa esteja encapsulado)
        try:
            iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='google'], iframe[id*='map']"))
            )
            print("🖼️ Entrando no Iframe do mapa...")
            driver.switch_to.frame(iframe)
        except:
            print("ℹ️ Verificando mapa na raiz (sem iframe)...")

        # 4. ESPERA DO GOOGLE MAPS (A Chave do Sucesso) 🗝️
        print("⏳ Aguardando renderização do Google Maps...")
        try:
            # Espera a classe padrão do Google Maps aparecer. Se isso não aparecer, o mapa quebrou.
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "gm-style"))
            )
            print("✅ Mapa Google carregado! Esperando pinos...")
            time.sleep(15) # Dá 15s para os pinos "caírem" no mapa (Blazor é lento)
        except:
            print("❌ ERRO CRÍTICO: O Google Maps não carregou.")
            # Lê o texto da tela para ver se tem erro de API ou WebGL
            texto_tela = driver.find_element(By.TAG_NAME, "body").text[:500]
            print(f"📝 Texto visível na tela: {texto_tela}")
            driver.switch_to.default_content()
            return

        # 5. CONTAGEM VIA JAVASCRIPT (Blindada)
        print("💉 Injetando Scanner de Marcadores...")
        
        script = """
            // Tenta achar marcadores modernos (Advanced) e antigos (Legacy)
            const markersAdv = document.querySelectorAll('gmp-advanced-marker');
            const markersLeg = document.querySelectorAll('div[role="button"][title]'); // Pinos clássicos
            const imgsPin = document.querySelectorAll('img[src*="pin-"]'); // Imagens soltas

            let dados = { verde: 0, vermelho: 0, amarelo: 0, total: 0 };
            
            // Função auxiliar para checar cor
            function checarCor(txt) {
                txt = txt.toLowerCase();
                if (txt.includes('verde') || txt.includes('livre')) return 'verde';
                if (txt.includes('vermelho') || txt.includes('ocupado')) return 'vermelho';
                if (txt.includes('amarelo')) return 'amarelo';
                return 'vermelho'; // Padrão
            }

            // 1. Prioridade: Marcadores Avançados (Shadow DOM)
            markersAdv.forEach(m => {
                dados.total++;
                // Tenta ler HTML interno ou titulo
                let conteudo = m.innerHTML + (m.getAttribute('title') || '');
                let cor = checarCor(conteudo);
                dados[cor]++;
            });

            // 2. Se não achou avançados, tenta os pinos normais (Fallback)
            if (dados.total === 0) {
                // Conta imagens diretas se existirem
                imgsPin.forEach(img => {
                    dados.total++;
                    let cor = checarCor(img.src);
                    dados[cor]++;
                });
            }

            return dados;
        """
        
        resultado = driver.execute_script(script)
        
        imgs_verde = resultado.get('verde', 0)
        imgs_vermelho = resultado.get('vermelho', 0)
        imgs_amarelo = resultado.get('amarelo', 0)
        frota_ativa = resultado.get('total', 0)
        
        print(f"🔢 Leitura Final: Total={frota_ativa} (Verde:{imgs_verde}/Vermelho:{imgs_vermelho})")

        # Se ainda der zero, vamos ver se tem Clusters (Bolinhas)
        total_clusters = 0
        if frota_ativa == 0:
            try:
                # Procura divs com números pequenos (clusters)
                divs = driver.find_elements(By.XPATH, "//div[text() and string-length(text())<=3]")
                for d in divs:
                    if d.text.isdigit() and d.size['width'] < 60:
                        total_clusters += int(d.text)
            except: pass
            
            if total_clusters > 0:
                print(f"📦 Clusters detectados: {total_clusters} veículos agrupados.")
                frota_ativa = total_clusters
                imgs_vermelho = total_clusters # Assume ocupado

        # 6. RELATÓRIOS
        ocupados = imgs_vermelho
        livres = imgs_verde
        
        # Sai do iframe
        driver.switch_to.default_content()

        if frota_ativa > 0:
            # Salva Pico
            if frota_ativa > estatisticas_dia['pico']:
                estatisticas_dia['pico'] = frota_ativa
                estatisticas_dia['hora_pico'] = time.strftime('%H:%M')
                salvar_dados()

            porc = round((ocupados / frota_ativa) * 100)
            situacao = "🟢" if porc < 40 else "🟡" if porc < 75 else "🔴 ALTA"

            msg_stats = (
                f"📊 *STATUS DA FROTA | {time.strftime('%H:%M')}*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{situacao} - {porc}% ocupado\n\n"
                f"🟢 Disponíveis: {livres}\n"
                f"🔴 Em Corrida: {ocupados}\n"
                f"🟡 Sem Rede: {imgs_amarelo}\n"
                f"🚗 Total Online: {frota_ativa}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            enviar_mensagem_evolution(msg_stats, NOME_GRUPO_AVISOS)
            time.sleep(1)

            # Alerta Reforço
            agora = time.time()
            if (porc >= PORCENTAGEM_CRITICA_OCUPACAO) and ((agora - ultimo_aviso_reforco)/60 >= TEMPO_COOLDOWN_REFORCO):
                enviar_mensagem_evolution(f"⚠️ *REFORÇO NECESSÁRIO:* Demanda alta ({porc}%).", NOME_GRUPO_AVISOS)
                ultimo_aviso_reforco = agora
        else:
            print("⚠️ Mapa carregou mas está vazio (Zoom ou sem carros).")

    except Exception as e: 
        print(f"❌ Erro Frota: {e}")
        try: driver.switch_to.default_content()
        except: pass

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
                # Nome corrigido aqui 👇
                tarefa_monitorar_frota(driver); t_frota = agora + (TEMPO_FROTA * 60)
            
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