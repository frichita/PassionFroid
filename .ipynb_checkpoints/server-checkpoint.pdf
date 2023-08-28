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

ACCOUNT_NAME = 'passionfroid'
ACCOUNT_KEY = os.getenv('ACCOUNT_KEY')
CONTAINER_NAME = 'passion-froid'
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

@app.route('/update/<blob_name>', methods=['POST'])
def update_image(blob_name):
    try:
        image = request.files.get('image')

        if not image:
            return jsonify({'error': 'No image provided'}), 400

        # Suppression de l'ancien blob
        old_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
        old_blob_client.delete_blob()

        # Upload de la nouvelle image
        new_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=secure_filename(image.filename))
        new_blob_client.upload_blob(image.read())
        new_blob_url = new_blob_client.url

        # Mise à jour dans MongoDB
        mongo.db.images.update_one({'image_path': old_blob_client.url}, {'$set': {'image_path': new_blob_url}})

        return jsonify({'message': new_blob_url}), 200

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
# La fonction de renommage d'une image de la base de données et de Azure Storage
def rename_blob(old_blob_name):
    new_name = request.form.get("new_name")

    # Récupération de la connexion Azure Blob
    blob_service_client = BlobServiceClient.from_connection_string("your_connection_string_here")
    blob_client = blob_service_client.get_blob_client(container="passion-froid", blob=old_blob_name)

    # Renommage du fichier dans Azure Storage en le copiant et en supprimant l'original
    blob_service_client.get_blob_client(container="passion-froid", blob=new_name).start_copy_from_url(blob_client.url)
    blob_client.delete_blob()

    # Mise à jour du nom du fichier dans la base de données
    if database_module.update_image_name(old_blob_name, new_name):
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
    other_field = request.form.get('otherField')

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
    
    # On initialise Azure Cognitive Services client
    computervision_client = ComputerVisionClient(
        "https://passion-froid-vision.cognitiveservices.azure.com/",
        CognitiveServicesCredentials("aacfabf84826411baf568cbad2c51c4a")
    )
    
    # Analyze image using Azure Computer Vision API
    image_analysis = computervision_client.analyze_image_in_stream(
        io.BytesIO(image_bytes),
        visual_features=[VisualFeatureTypes.tags, VisualFeatureTypes.description]
    )
    
    tags = [tag.name for tag in image_analysis.tags]
    description = image_analysis.description.captions[0].text if image_analysis.description.captions else ""

    # On insert les données dans la base de données
    data = {
        'image_path': blob_url,
        'other_field': other_field,
        'tags': tags,  # New field for tags
        'meta_description': description  # Updated with generated description
    }
    mongo.db.images.insert_one(data)

    return jsonify({'message': 'Success'}), 200

if __name__ == "__main__":
    app.run(debug=True)
