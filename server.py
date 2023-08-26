from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_pymongo import PyMongo
from flask import render_template
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials
import os
import io

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

ACCOUNT_NAME = 'passionfroid'
ACCOUNT_KEY = 'HuL6tfRJysTzKJDgo0YG/ML6M1UYJMdmFUEHUEvobVrB6SesnqJPkvAfq/6W7/mN+NfTl1V/5mIo+AStuFfDWg=='
CONTAINER_NAME = 'passion-froid'
BLOB_SERVICE = BlobServiceClient(account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net", credential=ACCOUNT_KEY)
CONTAINER_CLIENT = BLOB_SERVICE.get_container_client(CONTAINER_NAME)

SUBSCRIPTION_KEY = "472be19f-4437-4866-9a98-938aa71fd15e"
ENDPOINT = "aacfabf84826411baf568cbad2c51c4a"

computervision_client = ComputerVisionClient(ENDPOINT, CognitiveServicesCredentials(SUBSCRIPTION_KEY))

app.config["MONGO_URI"] = "mongodb://localhost:27017/passionFroid"
mongo = PyMongo(app)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/gallery', methods=['GET'])
def show_images():
    # Récupérer les noms de tous les blobs dans le conteneur
    blob_list = CONTAINER_CLIENT.list_blobs()
    blob_urls = [f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{blob.name}" for blob in blob_list]

    # Récupérer les métadonnées depuis MongoDB
    images_data = mongo.db.images.find({"image_path": {"$in": blob_urls}})
    
    image_list = []

    for image_data in images_data:
        image_dict = {
            "image_path": image_data['image_path'],
            "tags": image_data.get('tags', []),
            "meta_description": image_data.get('meta_description', '')
        }
        image_list.append(image_dict)

    # Retourner une réponse JSON
    return jsonify({'images': image_list})

@app.route('/update/<blob_name>', methods=['POST'])
def update_image(blob_name):
    try:
        image = request.files.get('image')

        if not image:
            return jsonify({'error': 'No image provided'}), 400

        # Supprimer l'ancien blob
        old_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
        old_blob_client.delete_blob()

        # Upload du nouvel image
        new_blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=secure_filename(image.filename))
        new_blob_client.upload_blob(image.read())
        new_blob_url = new_blob_client.url

        # Mise à jour dans MongoDB (si nécessaire)
        mongo.db.images.update_one({'image_path': old_blob_client.url}, {'$set': {'image_path': new_blob_url}})

        return jsonify({'message': new_blob_url}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete/<blob_name>', methods=['DELETE'])
def delete_image(blob_name):
    try:
        blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
        blob_client.delete_blob()

        # Si vous souhaitez également supprimer les données de MongoDB :
        mongo.db.images.delete_one({'image_path': blob_client.url})

        return jsonify({'message': 'Success'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_image():
    image = request.files.get('image')
    other_field = request.form.get('otherField')

    if not image:
        return jsonify({'error': 'No image provided'}), 400
    
    image_filename = secure_filename(image.filename)
    
    # Check if blob already exists
    blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=image_filename)
    if blob_client.exists():
        return jsonify({'error': 'Image already exists'}), 409

    # Read image into memory
    image_bytes = image.read()

    # Upload to Azure Blob Storage
    blob_client.upload_blob(image_bytes)
    blob_url = blob_client.url
    
    # Initialize Azure Cognitive Services client
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

    # Insert data into MongoDB
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
