from flask import Flask, request, jsonify
from utils import verify_quality, find_face_in_pdf
from PIL import Image
import tempfile
import os
from deepface import DeepFace

app = Flask(__name__)

# Store face temporarily for second step
TEMP_FACE_PATH = "badge_face_temp.jpg"

@app.route('/validate_photo', methods=['POST', 'GET'])
def validate_photo():
    file = request.files.get("photo")
    if not file:
        return jsonify({"error": "Aucun fichier reçu"}), 400

    try:
        image = Image.open(file)
        valid, message, face = verify_quality(image)

        if face:
            face.save(TEMP_FACE_PATH)

        return jsonify({
            "valid": valid,
            "message": message,
            "comparison_possible": bool(face)
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/match_faces', methods=['POST'])
def match_faces():
    cin_file = request.files.get("cin")
    if not cin_file:
        return jsonify({"error": "Fichier CIN manquant"}), 400

    if not os.path.exists(TEMP_FACE_PATH):
        return jsonify({"error": "Visage de badge non trouvé. Validez d'abord la photo."}), 400

    try:
        face_img, page, msg = find_face_in_pdf(cin_file)
        if face_img is None:
            return jsonify({"match": False, "message": msg}), 200

        # Save CIN face
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp:
            face_img.save(temp.name)
            cin_face_path = temp.name

        # Compare with saved badge face
        result = DeepFace.verify(
            img1_path=TEMP_FACE_PATH,
            img2_path=cin_face_path,
            model_name="ArcFace",
            distance_metric="cosine",
            enforce_detection=True
        )
        
        distance = result["distance"]
        threshold = 0.5
        if distance < threshold:
            message = "La photo correspond bien au visage figurant sur la CIN."
        else:
            message = "Les visages ne correspondent pas."
        os.remove(cin_face_path)

        return jsonify({
            "match": result["verified"],
            "distance": distance,
            "Seuil" : threshold,
            "message": message
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
