import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    # A porta será lida do ambiente, com 8080 como padrão.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
