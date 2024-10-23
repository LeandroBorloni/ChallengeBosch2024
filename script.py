import cv2
from gtts import gTTS
import threading
import queue
import inference
import os
import time
import speech_recognition as sr
import platform # Usar para feedback auditivo (Windows)
import pygame # Usar para feedback auditivo (Windows)
import uuid  # Para gerar nomes de arquivos únicos
import spacy  # Biblioteca para NLP (instalar com pip install spacy)

# Lista de preços dos produtos
precos_produtos = {
    'agua-garrafa': 2.50,
    'caixa-sucrilhos': 12.00,
    'coca-garrafa': 7.50,
    'coca-lata': 4.50,
    'coca-zero-garrafa': 7.50,
    'coca-zero-lata': 4.50,
    'doritos': 10.00,
    'fanta-laranja-garrafa': 6.90,
    'fanta-laranja-lata': 3.20,
    'guarana-garrafa': 6.70,
    'guarana-lata': 3.20,
    'guarana-zero-garrafa': 6.70,
    'guarana-zero-lata': 3.20,
    'heineken': 9.50,
    'saco-arroz': 25.00
}

# Carrega o modelo de linguagem português do spaCy
nlp = spacy.load("pt_core_news_sm")

# Função para converter texto em fala usando gTTS
def speak_gtts(text, queue_type="voice"):
    # Gerar um nome de arquivo único
    unique_id = str(uuid.uuid4())
    audio_file = f"temp_{queue_type}_{unique_id}.mp3"
    
    tts = gTTS(text=text, lang='pt-br')
    tts.save(audio_file)
    
    # Usar no Windows
    if platform.system() == "Windows":
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)  # Espera enquanto o áudio está sendo reproduzido
        except Exception as e:
            print(f"Erro ao reproduzir o áudio no Windows: {e}")
        finally:
            pygame.mixer.quit()  # Fecha o mixer do pygame
            # Remover o arquivo de áudio após reprodução
            if os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except Exception as e:
                    print(f"Erro ao remover o arquivo: {e}")
    else:
        # Usar no Linux ou Raspberry Pi OS
        try:
            os.system(f"mpg321 {audio_file}")
            os.remove(audio_file)  # Remover o arquivo após execução
        except Exception as e:
            print(f"Erro ao reproduzir o áudio no Linux/Raspberry Pi: {e}")

# Funções para gerenciar filas de fala separadas
def speech_worker_voice():
    while True:
        text = voice_speak_queue.get()
        if text is None:  # Exiting condition
            continue
        speak_gtts(text, "voice")
        voice_speak_queue.task_done()

def speech_worker_detection():
    while True:
        text = detection_speak_queue.get()
        if text is None:  # Exiting condition
            continue
        speak_gtts(text, "detection")
        detection_speak_queue.task_done()

# Função para adicionar mensagens na fila de voz
def speak_thread_voice(text):
    voice_speak_queue.put(text)

# Função para adicionar mensagens na fila de detecção
def speak_thread_detection(text):
    detection_speak_queue.put(text)

# Função para verificar se o objeto retornou ao campo de visão
def is_object_in_view(current_bbox, previous_bbox):
    x1_current, y1_current, x2_current, y2_current = current_bbox
    x1_prev, y1_prev, x2_prev, y2_prev = previous_bbox

    ix1 = max(x1_current, x1_prev)
    iy1 = max(y1_current, y1_prev)
    ix2 = min(x2_current, x2_prev)
    iy2 = min(y2_current, y2_prev)

    inter_width = max(0, ix2 - ix1)
    inter_height = max(0, iy2 - iy1)
    intersection_area = inter_width * inter_height

    current_area = (x2_current - x1_current) * (y2_current - y1_current)
    previous_area = (x2_prev - x1_prev) * (y2_prev - y1_prev)

    overlap_threshold = 0.2
    required_intersection_area = max(current_area, previous_area) * overlap_threshold

    return intersection_area > required_intersection_area

# Função para capturar áudio e reconhecer comandos de voz
def recognize_voice():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    
    with mic as source:
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)
    
    try:
        text = recognizer.recognize_google(audio, language='pt-BR')
        return text.lower()
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        speak_thread_voice(f"Erro no serviço de reconhecimento de voz")
        return None

# Função para interpretar o comando usando NLP
def interpret_command(text):
    doc = nlp(text)
    intent = None
    item = None

    # Simples análise de intenção com variações mais flexíveis
    if any(word in text for word in ["adicionar", "incluir", "acrescentar", "inserir"]):
        intent = "adicionar_item"
    elif any(word in text for word in ["remover", "retirar", "excluir", "descartar"]):
        intent = "remover_item"
    elif any(word in text for word in ["apagar", "limpar", "deletar", "esvaziar", "excluir"]) and "lista" in text:
        intent = "apagar_lista"
    elif any(word in text for word in ["ver", "mostrar", "listar", "exibir", "revisar"]) and "lista" in text:
        intent = "ver_lista"
    elif any(word in text for word in ["detectar", "identificar", "localizar", "encontrar", "reconhecer"]) and "objetos" in text:
        intent = "detectar_objetos"
    elif any(word in text for word in ["parar", "interromper", "cessar", "desativar", "finalizar"]):
        if "detecção" in text or "objetos" in text:
            intent = "parar_detecção"
    
    else:
        intent = None  

    # Extração de entidades (nomes de produtos)
    for token in doc:
        if token.text.lower() in produtos:  # Exemplo de como pegar um item (adapte conforme suas necessidades)
            item = token.text.lower()
            break

    return intent, item

# Função para gerenciar a lista de compras
def add_to_list(item):
    shopping_list.append(item)
    speak_thread_voice(f"{item} adicionado à lista de compras.")

def remove_from_list(item):
    if item in shopping_list:
        shopping_list.remove(item)
        speak_thread_voice(f"{item} removido da lista de compras.")
    else:
        speak_thread_voice(f"{item} não está na lista.")

# Função para apagar a lista de compras
def clear_list():
    shopping_list.clear()
    speak_thread_voice("Lista de compras apagada.")

# Função para listar a lista de compras atual
def speak_shopping_list():
    if shopping_list:
        items = ", ".join(shopping_list)
        total = sum(precos_produtos.get(item, 0) for item in shopping_list)  # Soma dos preços
        speak_thread_voice(f"A lista de compras atual contém: {items}. E o valor total da lista é {total:.2f} reais.")
    else:
        speak_thread_voice("A lista de compras está vazia.")

# Função para processar comandos de voz do usuário com NLP
def process_voice_commands():
    global detecting_objects
    while True:
        print("Aguardando novo comando de voz...")
        command_text = recognize_voice()
        print(f"Comando recebido: {command_text}")
        if command_text:
            intent, item = interpret_command(command_text)
            
            if intent == "apagar_lista":
                clear_list()
            elif intent == "ver_lista":
                speak_shopping_list()
            elif intent == "detectar_objetos":
                detecting_objects = True
                speak_thread_voice("Detecção iniciada.")
            elif intent == "parar_detecção":
                detecting_objects = False
                speak_thread_voice("Detecção finalizada.")
            # elif intent == "adicionar_item" and item:
            #     add_to_list(item)
            # elif intent == "remover_item" and item:
            #     remove_from_list(item)
            # elif intent:
            #     speak_thread_voice("Desculpe, não entendi o que você disse.")

# Função para verificar e responder à detecção de objetos
def handle_object_detected(class_name):
    preco = precos_produtos.get(class_name, "preço não disponível")
    speak_thread_detection(f"{class_name}, {preco} reais. Deseja adicionar ou remover da lista?")
    time.sleep(5)

    command_text = recognize_voice()
    
    if command_text:
        intent, item = interpret_command(command_text)
        if intent == "adicionar_item":
            add_to_list(class_name)
        elif intent == "remover_item":
            remove_from_list(class_name)
        else:
            speak_thread_voice("Não entendi sua intenção. Continuando a detecção.")
    else:
        speak_thread_voice("Continuando a detecção.")
    
    time.sleep(3)

# Funções de gerenciamento de lista de compras
shopping_list = []
produtos = ['agua-garrafa', 'caixa-sucrilhos', 'coca-garrafa','coca-lata', 'coca-zero-garrafa', 'coca-zero-lata', 
            'doritos', 'fanta-laranja-garrafa', 'fanta-laranja-lata', 'guarana-garrafa', 'guarana-lata', 'guarana-zero-garrafa', 
            'guarana-zero-lata', 'heineken', 'saco-arroz']

# Configuração inicial
detecting_objects = False
is_program_running = True

# Iniciar as filas de fala
voice_speak_queue = queue.Queue()
detection_speak_queue = queue.Queue()

# Threads separadas para fala
voice_worker_thread = threading.Thread(target=speech_worker_voice, daemon=True)
detection_worker_thread = threading.Thread(target=speech_worker_detection, daemon=True)

voice_worker_thread.start()
detection_worker_thread.start()

# Iniciar thread para comandos de voz
voice_thread = threading.Thread(target=process_voice_commands, daemon=True)
voice_thread.start()

# Carregar o modelo
model = inference.get_model("1-modelo/4")

# Iniciar a captura de vídeo
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 500)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 500)
# cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))

if not cap.isOpened():
    speak_thread_voice("Erro ao abrir a câmera.")
    exit()
            
# Dicionário para armazenar a visibilidade dos objetos
object_visibility = {}
frame_count = 0
process_frame_interval = 8

# Loop principal de captura de vídeo e reconhecimento de comandos
while is_program_running:
    if detecting_objects:
        # Captura frame a frame
        ret, frame = cap.read()
        
        if not ret:
            speak_thread_voice("Não foi possível capturar a imagem.")
            continue
        
        frame_count += 1
        
        if frame_count % process_frame_interval == 0:
            # Processar a imagem com o modelo
            result = model.infer(image=frame)
            
            current_objects = {}  # Dicionário para armazenar objetos detectados no frame atual

            if isinstance(result, list) and len(result) > 0:
                for response in result:
                    if response and response.predictions:
                        for prediction in response.predictions:
                            if prediction.confidence >= 0.5:
                                # Extraindo informações das previsões
                                x = int(prediction.x)
                                y = int(prediction.y)
                                width = int(prediction.width)
                                height = int(prediction.height)

                                x1 = int(x - width / 2)
                                y1 = int(y - height / 2)
                                x2 = int(x + width / 2)
                                y2 = int(y + height / 2)

                                confidence = prediction.confidence
                                class_name = prediction.class_name

                                # Adicionar o objeto detectado ao dicionário atual
                                current_objects[class_name] = (x1, y1, x2, y2)

                                # Desenhando a caixa delimitadora na imagem
                                color = (0, 255, 0)  # Verde para a caixa delimitadora
                                thickness = 2  # Espessura da linha da caixa

                                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

                                # Adicionando o texto com a classe e confiança
                                label = f"{class_name} ({confidence:.2f})"
                                cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                                # Verificar e falar sobre novos objetos ou objetos que retornaram
                                for class_name, bbox in current_objects.items():
                                    if class_name not in object_visibility:
                                        # O objeto é novo, fale sobre ele
                                        handle_object_detected(class_name)

            # Atualizar a visibilidade dos objetos
            object_visibility = current_objects

            # Exibe a imagem com o resultado
            cv2.imshow('Webcam', frame)
            cv2.waitKey(1)

cap.release()
cv2.destroyAllWindows()

# Finalizar a thread de fala
voice_speak_queue.put(None)
detection_speak_queue.put(None)
voice_worker_thread.join()
detection_worker_thread.join()
voice_thread.join()
