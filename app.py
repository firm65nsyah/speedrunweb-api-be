from api.index import app

if __name__ == "__main__":
    print("Menjalankan Speedrun API di http://127.0.0.1:5000 ...")
    app.run(host="0.0.0.0", port=5000, debug=True)
