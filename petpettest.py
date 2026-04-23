import os
preset_path = r"Prissets\SlipperOff\Sprites"
petpet_path = os.path.join(preset_path, "PetPet", "sprite.png")
print(os.path.exists(petpet_path), petpet_path)
