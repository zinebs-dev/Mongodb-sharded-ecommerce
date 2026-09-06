import os
import numpy as np
from flask import Flask, request, jsonify, render_template
from keras.applications.vgg16 import VGG16, preprocess_input
from keras.preprocessing.image import img_to_array, load_img
from sklearn.metrics.pairwise import cosine_similarity
from pymongo import MongoClient, errors
from tqdm import tqdm  
import random
import gc
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/images/products'
app.config['MAX_PRODUCTS'] = 1000  
app.config['BATCH_SIZE'] = 100
app.config['SIMILARITY_LIMIT'] = 200

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('templates', exist_ok=True)

def get_mongodb_connection():
    try:
        clint = MongoClient(
            "mongodb://localhost:27017/",
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            readPreference='primaryPreferred',  
            retryWrites=True,
            appname="AmazonStyleFinder"
        )
        client.admin.command('ping')
        print("Connexion MongoDB réussie")
        return client
    except errors.ServerSelectionTimeoutError as e:
        print(f"Erreur connexion MongoDB: {e}")
        try:
            print("Tentative de connexion alternative...")
            client = MongoClient(
                "mongodb://localhost:27017/",
                serverSelectionTimeoutMS=15000,
                connectTimeoutMS=15000
            )
            client.admin.command('ping')
            print("Connexion alternative réussie")
            return client
        except Exception as e2:
            print(f"Échec connexion alternative: {e2}")
            return None

client = get_mongodb_connection()
if client is None:
    print("Impossible de se connecter à MongoDB. Vérifiez votre cluster.")
    exit()

db = client["amazondb"]
products_collection = db["products"]

print("Chargement du modèle VGG16...")
model = VGG16(weights='imagenet', include_top=False)
print(" VGG16 chargé")

def safe_mongodb_operation(operation, *args, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return operation(*args, **kwargs)
        except errors.AutoReconnect as e:
            print(f"Tentative {attempt + 1}/{max_retries} - Reconnexion automatique...")
            if attempt == max_retries - 1:
                raise e
        except errors.ServerSelectionTimeoutError as e:
            print(f"Tentative {attempt + 1}/{max_retries} - Timeout serveur...")
            if attempt == max_retries - 1:
                raise e

def extract_features(image_path):
    try:
        if not os.path.exists(image_path):
            print(f"Image non trouvée : {image_path}")
            return None
        img = load_img(image_path, target_size=(224, 224))
        img_array = img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        img_array = preprocess_input(img_array)
        features = model.predict(img_array, verbose=0)
        return features.flatten().tolist()
    except Exception as e:
        print(f"Erreur extraction features pour {image_path}: {e}")
        return None

def update_sample_features(sample_size=1000):
    print(f"Mise à jour des features pour {sample_size} images...")
    try:
        all_products = safe_mongodb_operation(
            lambda: list(products_collection.find(
                {"imagePath": {"$exists": True}}, 
                {"_id": 1, "imagePath": 1}
            ))
        ) 
        print(f"{len(all_products)} produits avec imagePath trouvés")
        if len(all_products) == 0:
            print("Aucun produit avec imagePath trouvé dans la base")
            return 
        if len(all_products) > sample_size:
            sample_products = random.sample(all_products, sample_size)
        else:
            sample_products = all_products     
        print(f"{len(sample_products)} produits à traiter")
        success_count = 0
        batch_count = 0
        for i in range(0, len(sample_products), app.config['BATCH_SIZE']):
            batch = sample_products[i:i + app.config['BATCH_SIZE']]
            batch_count += 1
            print(f"Traitement du lot {batch_count} ({len(batch)} produits)")
            for product in tqdm(batch, desc=f"Lot {batch_count}"):
                try:
                    existing = safe_mongodb_operation(
                        lambda: products_collection.find_one(
                            {"_id": product["_id"], "features": {"$exists": True}}
                        )
                    )
                    if existing:
                        success_count += 1
                        continue
                    if "imagePath" not in product:
                        continue
                    image_path = product["imagePath"]
                    if not os.path.exists(image_path):
                        continue
                    features = extract_features(image_path)
                    if features:
                        safe_mongodb_operation(
                            lambda: products_collection.update_one(
                                {"_id": product["_id"]},
                                {"$set": {"features": features}}
                            )
                        )
                        success_count += 1
                except Exception as e:
                    print(f"Erreur avec le produit {product.get('_id', 'inconnu')}: {e}")
                    continue
            gc.collect()
        print(f"{success_count}/{len(sample_products)} produits traités avec succès")
    except Exception as e:
        print(f"Erreur lors de la mise à jour: {e}")

print("Initialisation de l'application...")
update_sample_features(app.config['MAX_PRODUCTS'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "Aucun fichier fourni"}), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "Aucun fichier sélectionné"}), 400
        print(f"Upload de l'image: {file.filename}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        print(f"Image sauvegardée: {file_path}")
        print("Extraction des features de l'image uploadée...")
        query_features = extract_features(file_path)
        if query_features is None:
            return jsonify({"error": "Impossible d'extraire les features de l'image"}), 500
        query_features = np.array(query_features)
        print("Features extraites avec succès")
        sample_products = safe_mongodb_operation(
            lambda: list(products_collection.find(
                {"features": {"$exists": True}}, 
                {"_id": 0, "features": 1, "productDisplayName": 1, "masterCategory": 1, 
                 "subCategory": 1, "baseColour": 1, "season": 1, "price": 1, "imagePath": 1}
            ).limit(app.config['SIMILARITY_LIMIT']))
        )
        print(f"{len(sample_products)} produits avec features disponibles pour la comparaison")
        if not sample_products:
            return jsonify({"error": "Aucun produit avec features disponibles dans la base."}), 404
        print("Calcul des similarités...")
        similarities = []
        for product in sample_products:
            try:
                if "features" not in product or not product["features"]:
                    continue
                product_features = np.array(product["features"])
                if query_features.shape != product_features.shape:
                    continue
                similarity = cosine_similarity([query_features], [product_features])[0][0]
                similarities.append({
                    "similarity": similarity,
                    "product": product
                })
            except Exception as e:
                continue
        print(f"{len(similarities)} produits valides pour la comparaison")
        if not similarities:
            return jsonify({"error": "Aucune similarité calculable avec les produits disponibles"}), 404
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        top_similarities = similarities[:4]
        top_products = []
        for data in top_similarities:
            product = data["product"]
            top_products.append({
                "productDisplayName": product["productDisplayName"],
                "masterCategory": product["masterCategory"],
                "subCategory": product["subCategory"],
                "baseColour": product["baseColour"],
                "season": product["season"],
                "price": product.get("price", "N/A"),
                "imagePath": product["imagePath"],
                "similarity_score": round(float(data["similarity"]), 4)
            })
        print(f"{len(top_products)} produits similaires trouvés")
        gc.collect()
        return jsonify(top_products)

    except Exception as e:
        print(f"Erreur dans /upload: {e}")
        return jsonify({"error": f"Erreur de connexion à la base de données. Vérifiez votre cluster MongoDB."}), 500

@app.route('/status')
def status():
    """Route pour vérifier le statut"""
    try:
        total_products = safe_mongodb_operation(
            lambda: products_collection.count_documents({})
        )
        products_with_features = safe_mongodb_operation(
            lambda: products_collection.count_documents({"features": {"$exists": True}})
        )
        products_with_imagepath = safe_mongodb_operation(
            lambda: products_collection.count_documents({"imagePath": {"$exists": True}})
        )
        
        return jsonify({
            "total_products": total_products,
            "products_with_features": products_with_features,
            "products_with_imagepath": products_with_imagepath,
            "max_products_used": app.config['MAX_PRODUCTS'],
            "similarity_limit": app.config['SIMILARITY_LIMIT'],
            "status": "OK"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/test-connection')
def test_connection():
    """Test de connexion aux shards"""
    try:
        client.admin.command('ping')
        test_doc = safe_mongodb_operation(
            lambda: products_collection.find_one({})
        )
        test_result = safe_mongodb_operation(
            lambda: products_collection.update_one(
                {"_id": test_doc["_id"] if test_doc else {"_id": "test"}},
                {"$set": {"last_test": datetime.now()}},
                upsert=True
            )
        )
        return jsonify({
            "connection": "OK",
            "read_operation": "OK" if test_doc else "No documents",
            "write_operation": "OK",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Démarrage du serveur Flask...")
    print(f"Configuration: MAX_PRODUCTS={app.config['MAX_PRODUCTS']}, SIMILARITY_LIMIT={app.config['SIMILARITY_LIMIT']}")
    app.run(debug=True, host='0.0.0.0', port=5000)