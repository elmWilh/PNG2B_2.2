import os
from app_paths import PRESETS_DIR, PRESET_AVATAR_DIR

preset_path = rf"{PRESETS_DIR}\SlipperOff\{PRESET_AVATAR_DIR}"
petpet_path = os.path.join(preset_path, "PetPet", "sprite.png")
print(os.path.exists(petpet_path), petpet_path)
