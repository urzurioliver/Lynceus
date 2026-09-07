from pymongo import MongoClient

# 1. Esta es la URL que te da MongoDB Atlas
uri = "mongodb+srv://<db_username>:16UXKwdBM351IpGl@cluster0.3kjiv9j.mongodb.net/?appName=Cluster0"

# 2. Creamos el cliente: es la conexión con MongoDB
client = MongoClient(uri)

# 3. Elegimos el nombre de nuestra base de datos
db = client["Lynceus"]

# 4. Elegimos una colección donde vamos a guardar mediciones
mediciones = db["mediciones"]

# 5. Probamos que la conexión funciona
client.admin.command("ping")

print("¡Conexión exitosa!")