import face_recognition
import numpy as np
from PIL import Image
import io


def encode_student_faces(student):
    """
    Encode le visage d'un étudiant et sauvegarde l'encodage

    Args:
        student: Instance du modèle Student

    Returns:
        bool: True si l'encodage a réussi, False sinon
    """
    if not student.photo:
        print(f"❌ Pas de photo pour {student.get_full_name()}")
        return False

    try:
        # Charger l'image
        image = face_recognition.load_image_file(student.photo.path)

        # Détecter les visages
        face_locations = face_recognition.face_locations(image)

        if len(face_locations) == 0:
            print(f"⚠️  Aucun visage détecté pour {student.get_full_name()}")
            return False

        if len(face_locations) > 1:
            print(f"⚠️  Plusieurs visages détectés pour {student.get_full_name()}, utilisation du premier")

        # Encoder le visage
        face_encodings = face_recognition.face_encodings(image, face_locations)

        if len(face_encodings) > 0:
            # Sauvegarder l'encodage
            student.set_face_encoding(face_encodings[0])
            student.save()
            print(f"✅ Visage encodé pour {student.get_full_name()}")
            return True
        else:
            print(f"❌ Impossible d'encoder le visage de {student.get_full_name()}")
            return False

    except Exception as e:
        print(f"❌ Erreur lors de l'encodage de {student.get_full_name()}: {str(e)}")
        return False


def find_matching_students(uploaded_photo_path, threshold=0.6):
    """
    Trouve les étudiants qui correspondent à une photo uploadée

    Args:
        uploaded_photo_path: Chemin vers la photo uploadée
        threshold: Seuil de distance (plus bas = plus strict). Par défaut 0.6

    Returns:
        list: Liste de tuples (student, similarity_score) triés par score décroissant
    """
    from .models import Student

    try:
        # Charger l'image uploadée
        uploaded_image = face_recognition.load_image_file(uploaded_photo_path)

        # Détecter les visages
        face_locations = face_recognition.face_locations(uploaded_image)

        if len(face_locations) == 0:
            print("❌ Aucun visage détecté sur la photo uploadée")
            return []

        if len(face_locations) > 1:
            print("⚠️  Plusieurs visages détectés, utilisation du premier")

        # Encoder le visage
        uploaded_encodings = face_recognition.face_encodings(uploaded_image, face_locations)

        if len(uploaded_encodings) == 0:
            print("❌ Impossible d'encoder le visage uploadé")
            return []

        uploaded_encoding = uploaded_encodings[0]

        # Récupérer tous les étudiants avec encodage
        students = Student.objects.exclude(face_encoding__isnull=True).exclude(face_encoding='')

        if students.count() == 0:
            print("⚠️  Aucun étudiant avec encodage facial dans la base")
            return []

        matches = []

        for student in students:
            try:
                student_encoding = student.get_face_encoding()

                if student_encoding is not None:
                    # Calculer la distance (plus c'est bas, plus c'est similaire)
                    distance = face_recognition.face_distance([student_encoding], uploaded_encoding)[0]

                    # Convertir la distance en score de similarité (0-100%)
                    similarity = (1 - distance) * 100

                    # Ne garder que si en dessous du seuil
                    if distance <= threshold:
                        matches.append({
                            'student': student,
                            'similarity': similarity,
                            'distance': distance
                        })

            except Exception as e:
                print(f"⚠️  Erreur pour {student.get_full_name()}: {str(e)}")
                continue

        # Trier par similarité décroissante
        matches.sort(key=lambda x: x['similarity'], reverse=True)

        print(f"✅ {len(matches)} correspondance(s) trouvée(s)")

        return matches

    except Exception as e:
        print(f"❌ Erreur lors de la recherche : {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def analyze_photo_quality(photo_path):
    """
    Analyse la qualité d'une photo

    Args:
        photo_path: Chemin vers la photo

    Returns:
        dict: Informations sur la qualité de la photo
    """
    try:
        image = face_recognition.load_image_file(photo_path)
        face_locations = face_recognition.face_locations(image)

        result = {
            'has_face': len(face_locations) > 0,
            'face_count': len(face_locations),
            'is_good_quality': False,
            'message': ''
        }

        if len(face_locations) == 0:
            result['message'] = "Aucun visage détecté"
        elif len(face_locations) > 1:
            result[
                'message'] = f"{len(face_locations)} visages détectés. Veuillez uploader une photo avec une seule personne."
        else:
            result['is_good_quality'] = True
            result['message'] = "Photo de bonne qualité"

        return result

    except Exception as e:
        return {
            'has_face': False,
            'face_count': 0,
            'is_good_quality': False,
            'message': f"Erreur: {str(e)}"
        }