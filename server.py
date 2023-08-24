from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_pymongo import PyMongo
from flask import render_template
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

ACCOUNT_NAME = 'passionfroid'
ACCOUNT_KEY = 'HuL6tfRJysTzKJDgo0YG/ML6M1UYJMdmFUEHUEvobVrB6SesnqJPkvAfq/6W7/mN+NfTl1V/5mIo+AStuFfDWg=='
CONTAINER_NAME = 'passion-froid'
BLOB_SERVICE = BlobServiceClient(account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net", credential=ACCOUNT_KEY)
CONTAINER_CLIENT = BLOB_SERVICE.get_container_client(CONTAINER_NAME)

app.config["MONGO_URI"] = "mongodb://localhost:27017/passionFroid"
mongo = PyMongo(app)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/gallery', methods=['GET'])
def show_images():
    # Récupérer les noms de tous les blobs dans le conteneur
    blob_list = CONTAINER_CLIENT.list_blobs()
    image_urls = [f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{blob.name}" for blob in blob_list]

    # Retourner une réponse JSON
    return jsonify({'image_urls': image_urls})

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

    # Enregistrement de l'image
    image_path = os.path.join(UPLOAD_FOLDER, secure_filename(image.filename))
    image.save(image_path)

    # Upload to Azure Blob Storage
    blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=secure_filename(image.filename))
    with open(image_path, "rb") as data:
        blob_client.upload_blob(data)
    blob_url = blob_client.url
    
    # Supprimer l'image locale après l'envoi
    os.remove(image_path)

    # Insertion des données dans MongoDB
    data = {
        'image_path': blob_url,   # Utilisez l'URL du blob au lieu du chemin local
        'other_field': other_field
    }
    mongo.db.images.insert_one(data)

    return jsonify({'message': 'Success'}), 200

if __name__ == "__main__":
    app.run(debug=True)
