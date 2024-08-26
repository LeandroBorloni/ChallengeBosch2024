import cv2
import inference

# Carregar o modelo
model = inference.get_model("1-modelo/2")

# Iniciar a captura de vídeo
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Erro ao abrir a câmera.")
    exit()

while True:
    # Captura frame a frame
    ret, frame = cap.read()
    
    if not ret:
        print("Não foi possível capturar a imagem.")
        break

    # Processar a imagem com o modelo
    result = model.infer(image=frame)
    
    # Verifica se o resultado é uma lista e acessa o primeiro item
    if isinstance(result, list) and len(result) > 0:
        for response in result:
            if response and response.predictions:
                for prediction in response.predictions:
                    # Extraindo informações das previsões
                    x = int(prediction.x)
                    y = int(prediction.y)
                    width = int(prediction.width)
                    height = int(prediction.height)
                    confidence = prediction.confidence
                    class_name = prediction.class_name

                    # Desenhando a caixa delimitadora na imagem
                    top_left = (x, y)
                    bottom_right = (x + width, y + height)
                    color = (0, 255, 0)  # Verde para a caixa delimitadora
                    thickness = 2  # Espessura da linha da caixa

                    cv2.rectangle(frame, top_left, bottom_right, color, thickness)

                    # Adicionando o texto com a classe e confiança
                    label = f"{class_name} ({confidence:.2f})"
                    cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # Exibe a imagem com o resultado
    cv2.imshow('Webcam', frame)

    # Tecla 'q' pressionada para sair
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
