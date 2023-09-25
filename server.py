# Importation des bibliothèques
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_pymongo import PyMongo
from flask import render_template
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from werkzeug.datastructures import FileStorage
from msrest.authentication import CognitiveServicesCredentials
from dotenv import load_dotenv
from bson import ObjectId
import os
import io

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

ACCOUNT_NAME = 'passionfroid1'
ACCOUNT_KEY = os.getenv('ACCOUNT_KEY')
CONTAINER_NAME = 'passionfroid1'
BLOB_SERVICE = BlobServiceClient(account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net", credential=ACCOUNT_KEY)
CONTAINER_CLIENT = BLOB_SERVICE.get_container_client(CONTAINER_NAME)

SUBSCRIPTION_KEY = os.getenv('SUBSCRIPTION_KEY')
ENDPOINT = os.getenv('ENDPOINT')

computervision_client = ComputerVisionClient(ENDPOINT, CognitiveServicesCredentials(SUBSCRIPTION_KEY))

app.config["MONGO_URI"] = "mongodb://localhost:27017/passionFroid"
mongo = PyMongo(app)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/gallery', methods=['GET'])
def show_images():
    # Récupérer les paramètres de tri depuis la requête
    sort_by = request.args.get('sort_by', 'name')  # Par défaut, triez par nom du fichier
    order = int(request.args.get('order', 1))  # Par défaut, triez par ordre croissant

    # Récupérer les noms de tous les blobs du conteneur
    blob_list = CONTAINER_CLIENT.list_blobs()
    blob_urls = [f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{blob.name}" for blob in blob_list]

    # Récupérer les données depuis MongoDB en fonction des paramètres de tri
    if sort_by == 'name':
        images_data = mongo.db.images.find({"image_path": {"$in": blob_urls}}).sort("image_path", order)
    elif sort_by == 'nbRecherche':
        images_data = mongo.db.images.find({"image_path": {"$in": blob_urls}}).sort("nbRecherche", order)
    else:
        # Par défaut, triez par nom du fichier
        images_data = mongo.db.images.find({"image_path": {"$in": blob_urls}}).sort("image_path", order)

    image_list = []

    for image_data in images_data:
        image_dict = {
            "_id": image_data["_id"],  # Inclure l'ID
            "image_path": image_data['image_path'],
            "tags": image_data.get('tags', []),
            "meta_description": image_data.get('meta_description', ''),
            "nbRecherche": image_data.get('nbRecherche', 0)  # Inclure nbRecherche, 0 par défaut
        }
        image_list.append(image_dict)

    # Retourne une réponse JSON
    return jsonify({'images': image_list})

@app.route('/increment-nb-recherche/<int:image_id>', methods=['PUT'])
def increment_nb_recherche(image_id):
    try:
        # Récupérer l'image à partir de la base de données en utilisant l'ID
        image = mongo.db.images.find_one({'_id': image_id})

        if image is None:
            return jsonify({'error': 'Image not found'}), 404

        # Incrémenter nbRecherche
        new_nb_recherche = image['nbRecherche'] + 1

        # Mettre à jour nbRecherche dans la base de données
        mongo.db.images.update_one({'_id': image_id}, {'$set': {'nbRecherche': new_nb_recherche}})

        return jsonify({'message': 'nbRecherche incremented successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/delete/<blob_name>', methods=['DELETE'])
def delete_image(blob_name):
    try:
        blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
        blob_client.delete_blob()

        # Suppression des données de MongoDB :
        mongo.db.images.delete_one({'image_path': blob_client.url})

        return jsonify({'message': 'Success'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# La route pour rename un nom de fichier 
@app.route("/rename/<old_blob_name>", methods=["POST"])
def rename_blob(old_blob_name):
    new_name = request.form.get("new_name")
    
    # Extract the file extension from the old name
    file_extension = old_blob_name.split('.')[-1]

    # Generate the new blob name with the same file extension
    new_blob_name = f"{new_name}.{file_extension}"

    # Generate the full URLs for old and new blobs
    old_blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{old_blob_name}"
    new_blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{new_blob_name}"

    # Create a secure filename for the new blob name
    new_blob_name = secure_filename(new_blob_name)

    # Set up clients for the old and new blobs
    old_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=old_blob_name)
    new_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=new_blob_name)

    # Start copying the old blob's content to the new blob
    new_blob_client.start_copy_from_url(old_blob_client.url)

    # Delete the old blob
    old_blob_client.delete_blob()

    # Update the image path in MongoDB
    update_result = mongo.db.images.update_one(
        {'image_path': old_blob_url},
        {'$set': {'image_path': new_blob_url}}
    )

    if update_result.modified_count > 0:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "failure"}), 400

# La route pour upload l'image dans Azure Storage et sur MongoDB 
@app.route('/upload', methods=['POST'])
def upload_image():
    images = request.files.getlist('images')  # Utilisez getlist pour obtenir une liste d'images

    if not images:
        return jsonify({'error': 'No images provided'}), 400

    success_messages = []  # Liste pour stocker les messages de succès

    for image in images:
        image_filename = secure_filename(image.filename)

        # Vérifiez si le blob existe
        blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=image_filename)
        if blob_client.exists():
            return jsonify({'error': f'Image {image_filename} already exists'}), 409

        # Lisez l'image
        image_bytes = image.read()

        # Chargez l'image dans Azure
        blob_client.upload_blob(image_bytes)
        blob_url = blob_client.url

        # Générez la nouvelle clé primaire
        new_image_id = increment_image_id()

        # Initialisez le client Azure Cognitive Services
        computervision_client = ComputerVisionClient(
            "https://passionfroid.cognitiveservices.azure.com/",
            CognitiveServicesCredentials(ENDPOINT)
        )

        # Analysez l'image à l'aide de l'API Azure Computer Vision
        image_analysis = computervision_client.analyze_image_in_stream(
            io.BytesIO(image_bytes),
            visual_features=[VisualFeatureTypes.tags, VisualFeatureTypes.description]
        )

        tags = [tag.name for tag in image_analysis.tags]
        description = image_analysis.description.captions[0].text if image_analysis.description.captions else ""

        # Insérez les données dans la base de données avec la nouvelle clé primaire
        data = {
            '_id': new_image_id,
            'image_path': blob_url,
            'tags': tags,
            'meta_description': description,
            'nbRecherche': 0,  # Initialisez nbRecherche à 0
        }
        mongo.db.images.insert_one(data)

        success_messages.append(f'Image {image_filename} uploaded successfully')

    # Retournez un message de succès global
    return jsonify({'message': success_messages}), 200



def increment_image_id():
    # Incrémente la séquence et retourne la nouvelle valeur
    sequence_doc = mongo.db.counters.find_one_and_update(
        {'_id': 'images'},
        {'$inc': {'sequence_value': 1}},
        upsert=True,
        return_document=True
    )
    return sequence_doc['sequence_value']
if __name__ == "__main__":
    app.run(debug=True)
