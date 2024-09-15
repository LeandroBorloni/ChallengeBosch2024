import cv2
import pyttsx3
import threading
import queue
import inference

# Configurar o mecanismo de fala
engine = pyttsx3.init()
queue_lock = threading.Lock()
speak_queue = queue.Queue()

def speak(text):
    with queue_lock:
        engine.say(text)
        engine.runAndWait()

def speech_worker():
    while True:
        text = speak_queue.get()
        if text is None:  # Exiting condition
            break
        speak(text)
        speak_queue.task_done()

# Iniciar a thread de fala
worker_thread = threading.Thread(target=speech_worker, daemon=True)
worker_thread.start()

# Função para executar a fala na fila
def speak_thread(text):
    speak_queue.put(text)

# Função para verificar se o objeto retornou ao campo de visão
def is_object_in_view(current_bbox, previous_bbox):
    """
    Verifica se o objeto atual (current_bbox) está visível na mesma área geral
    onde estava anteriormente (previous_bbox).

    current_bbox: Tupla com as coordenadas da caixa delimitadora atual (x1, y1, x2, y2)
    previous_bbox: Tupla com as coordenadas da caixa delimitadora anterior (x1, y1, x2, y2)
    """
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

# Carregar o modelo
model = inference.get_model("1-modelo/3")

# Iniciar a captura de vídeo
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Erro ao abrir a câmera.")
    exit()

# Dicionário para armazenar a visibilidade dos objetos
object_visibility = {}

while True:
    # Captura frame a frame
    ret, frame = cap.read()
    
    if not ret:
        print("Não foi possível capturar a imagem.")
        break

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
            speak_thread(f"{class_name}")
        else:
            # O objeto já estava visível anteriormente, verifique se voltou
            if not is_object_in_view(bbox, object_visibility[class_name]):
                # O objeto saiu e voltou para o campo de visão, fale sobre ele
                speak_thread(f"{class_name}")

    # Atualizar a visibilidade dos objetos
    object_visibility = current_objects

    # Exibe a imagem com o resultado
    cv2.imshow('Webcam', frame)

    # Tecla 'q' pressionada para sair
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Fechar o vídeo e liberar os recursos
cap.release()
cv2.destroyAllWindows()

# Finalizar a thread de fala
speak_queue.put(None)
worker_thread.join()