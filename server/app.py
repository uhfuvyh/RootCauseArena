import sys
import os

# Link to the actual server script in the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server_v2 import app

def main():
    import uvicorn
    uvicorn.run("server_v2:app", host="0.0.0.0", port=7860, reload=False)

if __name__ == "__main__":
    main()
