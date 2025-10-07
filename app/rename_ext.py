import os

# Folder preview sesuai path kamu
target_folder = r"C:\web-lootpixel\static\previews"

# Ekstensi yang akan diubah
uppercase_exts = ['.PNG', '.JPG', '.JPEG', '.GIF']

# Rename semua file yang ekstensinya huruf besar ke huruf kecil
for filename in os.listdir(target_folder):
    filepath = os.path.join(target_folder, filename)
    name, ext = os.path.splitext(filename)

    if ext.upper() in uppercase_exts:
        new_filename = name + ext.lower()
        new_filepath = os.path.join(target_folder, new_filename)
        os.rename(filepath, new_filepath)
        print(f"Renamed: {filename} → {new_filename}")

print("✅ Semua ekstensi sudah diganti ke huruf kecil.")
