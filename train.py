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
    model=YOLO('best.pt')

    results = model.train(
        data='pothole_retrain_config.yaml',
        epochs=50, 
        imgsz=640,
        name='pothole_finetune_v2'
    )
   
if __name__ == "__main__":
    train_model()

