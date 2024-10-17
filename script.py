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
            break
        speak_gtts(text, "voice")
        voice_speak_queue.task_done()

def speech_worker_detection():
    while True:
        text = detection_speak_queue.get()
        if text is None:  # Exiting condition
            break
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
    if "gravar" in text or "criar" in text and "lista" in text:
        intent = "gravar_lista"
    elif "confirmar" in text:
        intent = "confirmar_item"
    elif "apagar" in text and "lista" in text:
        intent = "apagar_lista"
    elif "ver" in text and "lista" in text:
        intent = "ver_lista"
    elif "detectar" in text or "detecção" in text and "objetos" in text:
        intent = "detectar_objetos"
    elif "parar" in text or "finalizar" in text:
        if "detecção" in text or "objetos" in text:
            intent = "parar_detecção"
        elif "lista" in text:
            intent = "parar_lista"
    
    # Extração de entidades (nomes de produtos)
    for token in doc:
        if token.text.lower() in produtos:  # Exemplo de como pegar um item (adapte conforme suas necessidades)
            item = token.text.lower()
            break

    return intent, item

# Função para adicionar itens à lista de compras
def add_to_shopping_list():
    speak_thread_voice("Comece a dizer os itens da lista de compras.")
    temp_list = []  # Lista temporária para gravar os itens
    while True:
        command = recognize_voice()
        if command:
            intent, _ = interpret_command(command)
            if intent == "parar_lista":
                if temp_list:
                    # Fala todos os itens adicionados
                    items = ", ".join(temp_list)
                    speak_thread_voice(f"Sua lista atual contém os seguintes itens: {items}.")
                    
                    # Pergunta se deseja alterar algum item
                    speak_thread_voice("Deseja alterar algum item?")
                    time.sleep(2)
                    response = recognize_voice()

                    if response and "sim" in response:
                        speak_thread_voice("Regravando a lista de compras. Comece a dizer os itens novamente.")
                        add_to_shopping_list()  # Recomeça o processo de gravação da lista
                    else:
                        # Se a resposta for não, grava os itens na lista definitiva
                        shopping_list.extend(temp_list)
                        speak_thread_voice("Lista de compras gravada.")
                else:
                    speak_thread_voice("Nenhum item foi adicionado à lista.")
                break
            else:
                # Adiciona o item à lista temporária
                temp_list.append(command)

# Função para confirmar itens
def confirm_item(item):
    print(item)
    print(shopping_list)
    if item in shopping_list:
        print(f'Entrou no if: {item}')
        checked_items.append(item)
        shopping_list.remove(item)
        speak_thread_voice(f"{item} confirmado.")
    else:
        speak_thread_voice(f"{item} não está na lista.")

# Função para apagar a lista de compras
def clear_list():
    shopping_list.clear()
    checked_items.clear()
    speak_thread_voice("Lista de compras apagada.")

# Função para listar os itens restantes
def list_remaining_items():
    if shopping_list:
        remaining_items = ", ".join(shopping_list)
        speak_thread_voice(f"Faltam os seguintes itens: {remaining_items}.")
    else:
        speak_thread_voice("Todos os itens foram confirmados.")

# Função para listar a lista de compras atual
def speak_shopping_list():
    if shopping_list:
        items = ", ".join(shopping_list)
        speak_thread_voice(f"A lista de compras atual contém: {items}.")
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
            
            if intent == "gravar_lista":
                add_to_shopping_list()
            elif intent == "confirmar_item" and item:
                confirm_item(item)
                list_remaining_items()
            elif intent == "apagar_lista":
                clear_list()
            elif intent == "ver_lista":
                speak_shopping_list()
            elif intent == "detectar_objetos":
                detecting_objects = True
                speak_thread_voice("Detecção iniciada.")
            elif intent == "parar_detecção":
                detecting_objects = False
                speak_thread_voice("Detecção finalizada.")
            else:
                speak_thread_voice("Desculpe, não entendi o que você disse.")


# Funções de gerenciamento de lista de compras
shopping_list = []
checked_items = []
produtos = ['coca-cola', 'coca-cola zero', 'guarana', 'guarana zero', 'arroz', 'fanta laranja', 'feijao', 'agua']

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
model = inference.get_model("1-modelo/3")

# Iniciar a captura de vídeo
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 500)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 500)
# cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))

if not cap.isOpened():
    print("Erro ao abrir a câmera.")
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
            print("Não foi possível capturar a imagem.")
            break
        
        frame_count += 1
        
        if frame_count % process_frame_interval == 0:
            # Processar a imagem com o modelo
            result = model.infer(image=frame)
            
            current_objects = {}  # Dicionário para armazenar objetos detectados no frame atual

            if isinstance(result, list) and len(result) > 0:
                for response in result:
                    if response and response.predictions:
                        for prediction in response.predictions:
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
                    speak_thread_detection(f"{class_name}. ")
                else:
                    # O objeto já estava visível anteriormente, verifique se voltou
                    if not is_object_in_view(bbox, object_visibility[class_name]):
                        # O objeto saiu e voltou para o campo de visão, fale sobre ele
                        speak_thread_detection(f"{class_name}. ")

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
