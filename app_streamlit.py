import streamlit as st
import cv2
import numpy as np
from deepface import DeepFace
import tempfile
import os
from PIL import Image
from mtcnn import MTCNN
from pdf2image import convert_from_bytes
import fitz  # PyMuPDF
import mediapipe as mp

detector = MTCNN()

def is_scanned_pdf(file_path):
    with fitz.open(file_path) as doc:
        for page in doc:
            if page.get_text().strip():
                return False
    return True

def detect_face_mtcnn(image):
    img = np.array(image.convert('RGB'))
    detections = detector.detect_faces(img)
    if len(detections) == 0:
        return False, "Aucun visage détecté."
    return img, detections[0]

def check_face_orientation(image_pil):
    image = np.array(image_pil.convert("RGB"))
    mp_face_mesh = mp.solutions.face_mesh
    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True) as face_mesh:
        results = face_mesh.process(image)
        if not results.multi_face_landmarks:
            return False, "Aucun visage détecté avec MediaPipe."
        landmarks = results.multi_face_landmarks[0]
        left_eye = landmarks.landmark[33]
        right_eye = landmarks.landmark[263]
        nose_tip = landmarks.landmark[1]
        nose_center_x = (left_eye.x + right_eye.x) / 2
        nose_offset = abs(nose_tip.x - nose_center_x)
        if nose_offset > 0.03:
            return False, "Le visage n'est pas assez frontal."
        eye_diff_y = abs(left_eye.y - right_eye.y)
        if eye_diff_y > 0.02:
            return False, "La tête est inclinée."
        return True, "Orientation correcte"

def verify_quality(image_pil):
    result = detect_face_mtcnn(image_pil)
    if result[0] is False:
        return False, result[1], None

    img, face = result
    x, y, w, h = face['box']
    img_h, img_w = img.shape[:2]

    # 📏 Taille du visage
    taille_ok = w >= 0.2 * img_w and h >= 0.2 * img_h
    if not taille_ok:
        reason = "Le visage est trop petit ou éloigné."

    # 🎯 Centrage du visage
    face_center_x = x + w / 2
    face_center_y = y + h / 2
    centre_ok = abs(face_center_x - img_w / 2) <= img_w * 0.25 and abs(face_center_y - img_h / 2) <= img_h * 0.25
    if not centre_ok:
        reason = "Le visage doit être centré."

    # 👁️ Orientation (MediaPipe)
    orientation_ok, orientation_msg = check_face_orientation(image_pil)
    if not orientation_ok:
        reason = orientation_msg

    # 💡 Luminosité
    margin = 20
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(img_w, x + w + margin)
    y2 = min(img_h, y + h + margin)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    roi = gray[y1:y2, x1:x2]
    mean_brightness = np.mean(roi)
    luminosite_ok = 100 <= mean_brightness <= 210
    if not luminosite_ok:
        reason = "L'éclairage est trop faible." if mean_brightness < 100 else "La photo est surexposée."

    # 🖼️ Toujours extraire le visage s’il a été détecté
    face_crop_np = img[y1:y2, x1:x2]
    face_crop_pil = Image.fromarray(face_crop_np)

    # ✅ Tous les critères OK ?
    if taille_ok and centre_ok and orientation_ok and luminosite_ok:
        return True, "Photo valide pour le badge.", face_crop_pil
    else:
        return False, reason, face_crop_pil

def find_face_in_pdf(uploaded_file):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(uploaded_file.read())
            temp_pdf_path = temp_pdf.name
        #if not is_scanned_pdf(temp_pdf_path):
         #   return None, None, "❌ Le fichier PDF n'est pas un scan. Veuillez téléverser une CIN scannée."
        with open(temp_pdf_path, "rb") as f:
            pages = convert_from_bytes(f.read())
        if not pages:
            return None, None, "❌ Le fichier PDF est vide ou illisible."
        for idx, page in enumerate(pages):
            img_rgb = np.array(page.convert('RGB'))
            detections = detector.detect_faces(img_rgb)
            if detections:
                largest_face = max(detections, key=lambda d: d["box"][2] * d["box"][3])
                x, y, w, h = largest_face["box"]
                x, y = max(0, x), max(0, y)
                margin = 60
                x1 = max(0, x - margin)
                y1 = max(0, y - margin)
                x2 = min(img_rgb.shape[1], x + w + margin)
                y2 = min(img_rgb.shape[0], y + h + margin)
                if x2 <= x1 or y2 <= y1:
                    continue
                face_crop = page.crop((x1, y1, x2, y2)).convert("RGB")
                return face_crop, idx + 1, f"✅ Visage détecté à la page {idx + 1} du PDF."
        return None, None, "❌ Aucun visage détecté dans la CIN."
    except Exception as e:
        return None, None, f"❌ Erreur PDF : {str(e)}"

# 🧩 Interface utilisateur
st.title("🔍 Vérification de Photo + CIN")

# 1. 📸 Import et vérification automatique de la photo
img1 = st.file_uploader("📸 Téléversez une photo pour le badge", type=["jpg", "jpeg", "png"])
if img1:
    pil_img1 = Image.open(img1)
    valid, message, face = verify_quality(pil_img1)
    st.image(pil_img1, caption="Photo téléversée", use_column_width=True)

    if face is not None:
        st.session_state["badge_face"] = face
        if valid:
            st.success(f"✅ {message}")
        else:
            st.warning(f"⚠️ Photo invalide : {message} — mais un visage a été détecté, la comparaison est possible.")
    else:
        st.error(f"❌ Photo invalide : {message} — aucun visage détecté, la comparaison est impossible.")


    

# 2. 🪪 Import et vérification automatique de la CIN
cin_file = st.file_uploader("🪪 Téléversez votre CIN au format PDF scanné", type=["pdf"])
if cin_file:
    face_img, page_num, message = find_face_in_pdf(cin_file)
    if face_img is None:
        st.error(message)
    else:
        st.success(message)
        st.session_state["cin_face"] = face_img
        st.image(face_img, caption=f"Visage extrait de la CIN (page {page_num})", use_column_width=True)

# 3. 🔁 Comparaison si les deux images sont présentes
if st.session_state.get("badge_face") and st.session_state.get("cin_face"):
    st.markdown("### 🔁 Comparaison entre photo et visage extrait de la CIN")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp1:
        st.session_state["badge_face"].save(temp1.name)
        img1_path = temp1.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp2:
        st.session_state["cin_face"].save(temp2.name)
        img2_path = temp2.name
    try:
        result = DeepFace.verify(
            img1_path=img1_path,
            img2_path=img2_path,
            model_name="ArcFace",
            distance_metric="cosine",
            enforce_detection=True
        )
        
        distance = result["distance"]
        threshold = 0.5
        if distance < threshold:
            st.success("✅ La photo correspond bien au visage figurant sur la CIN.")
        else:
            st.error("❌ Les visages ne correspondent pas.")
        st.write(f"🧠 Distance : {distance:.4f} (Seuil : {threshold:4f})")
    except Exception as e:
        st.error(f"Erreur lors de la comparaison : {e}")
    finally:
        os.remove(img1_path)
        os.remove(img2_path)
