from ultralytics import YOLO
import yaml
import os


DATASET_CONFIG = {
    
    'path': os.path.abspath('retraining_dataset'), 
    'train': 'images',
    'val': 'images', 
    'names': {
        0: 'pothole'
    }
}

with open('pothole_retrain_config.yaml', 'w') as f:
    yaml.dump(DATASET_CONFIG, f)

def train_model():
    """
    Loads the existing 'best.pt' model and fine-tunes it using the new,
    verified data from the exported dataset.
    """
    print("Loading pre-trained model 'best.pt' for fine-tuning...")
    
    model = YOLO('best.pt')

    print("Starting fine-tuning process...")
    
    
    results = model.train(
        data='pothole_retrain_config.yaml',
        epochs=50, 
        imgsz=640,
        name='pothole_finetune_v2'
    )
    
    print("\n✅ Training complete! New model saved.")
    print("Find your new, improved model at: runs/detect/pothole_finetune_v2/weights/best.pt")

if __name__ == "__main__":
    train_model()

