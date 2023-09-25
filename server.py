# Importation des bibliothèques
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_pymongo import PyMongo
from flask import render_template
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials
from dotenv import load_dotenv
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
    # Récupérer les noms de tous les blobs du conteneur
    blob_list = CONTAINER_CLIENT.list_blobs()
    blob_urls = [f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{blob.name}" for blob in blob_list]

    # Récupérer les données depuis MongoDB
    images_data = mongo.db.images.find({"image_path": {"$in": blob_urls}})
    
    image_list = []

    for image_data in images_data:
        image_dict = {
            "image_path": image_data['image_path'],
            "tags": image_data.get('tags', []),
            "meta_description": image_data.get('meta_description', '')
        }
        image_list.append(image_dict)

    # Retourne une réponse JSON
    return jsonify({'images': image_list})


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
# La fonction de renommage d'une image de la base de données et de Azure Storage
def rename_blob(old_blob_name):
    new_name = request.form.get("new_name")

    # Generation  des anciens et nouveaux blobs
    old_blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{old_blob_name}"
    new_blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{new_name}"

    # Mise en place d'un client pour l'ancien blob
    old_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=old_blob_name)

    # Copie du nouveau nom dans le blob
    new_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=new_name)
    new_blob_client.start_copy_from_url(old_blob_client.url)

    # Suppression de l'ancien blob
    old_blob_client.delete_blob()

    # Mise à jour dans MongoDB
    update_result = mongo.db.images.update_one(
        {'image_path': old_blob_url},
        {'$set': {'image_path': new_blob_url}}
    )

    if update_result.modified_count > 0:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "failure"}), 400


# La route de recherche
@app.route('/search', methods=['GET'])
# La fonction qui recherche les tags des images
def search_images():
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    # Recherche dans MongoDB en utilisant un regex
    images_data = mongo.db.images.find({"tags": {"$regex": query, "$options": 'i'}})
    
    image_list = []

    for image_data in images_data:
        image_dict = {
            "image_path": image_data['image_path'],
            "tags": image_data.get('tags', []),
            "meta_description": image_data.get('meta_description', '')
        }
        image_list.append(image_dict)
    
    return jsonify({'images': image_list})

# La route pour upload l'image dans Azure Storage et sur MongoDB
@app.route('/upload', methods=['POST'])
def upload_image():
    image = request.files.get('image')

    if not image:
        return jsonify({'error': 'No image provided'}), 400
    
    image_filename = secure_filename(image.filename)
    
    # On check si le blob existe :
    blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=image_filename)
    if blob_client.exists():
        return jsonify({'error': 'Image already exists'}), 409

    # On lit l'image
    image_bytes = image.read()

    # on upload dans Azure 
    blob_client.upload_blob(image_bytes)
    blob_url = blob_client.url
    
    # On génère la nouvelle clé primaire
    new_image_id = increment_image_id()

    # On initialise Azure Cognitive Services client
    computervision_client = ComputerVisionClient(
        "https://passionfroid.cognitiveservices.azure.com/",
        CognitiveServicesCredentials(ENDPOINT)
    )
    
    # Analyze image using Azure Computer Vision API
    image_analysis = computervision_client.analyze_image_in_stream(
        io.BytesIO(image_bytes),
        visual_features=[VisualFeatureTypes.tags, VisualFeatureTypes.description]
    )
    
    tags = [tag.name for tag in image_analysis.tags]
    description = image_analysis.description.captions[0].text if image_analysis.description.captions else ""

    # On insert les données dans la base de données avec la nouvelle clé primaire
    data = {
        '_id': new_image_id,  # Nouvelle clé primaire incrémentée
        'image_path': blob_url,
        'tags': tags,
        'meta_description': description
    }
    mongo.db.images.insert_one(data)

    return jsonify({'message': 'Success'}), 200

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
