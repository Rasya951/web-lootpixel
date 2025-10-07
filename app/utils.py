import os
import io
import fitz  # PyMuPDF
from PIL import Image
from bs4 import BeautifulSoup
from reportlab.pdfgen import canvas
from PyPDF2 import PdfMerger
from flask_mail import Message
import hmac
import hashlib
from . import mail
from .models import db, SVGElement, LayoutHyperlink

# ========================
# PDF Generator (Full dengan Hyperlink SVG + DB)
# ========================
def generate_planner_pdf(config, output_path):
    product_id = config['product_id']
    orientation = config['orientation']
    ring = config['ring']
    tab = config['tab']
    weekly = config['weekly_layout']
    daily = config['daily_layout']
    start_day = config['start_day']

    base_path = f"static/assets/{product_id}/{orientation}"
    os.makedirs("temp", exist_ok=True)
    
    # Definisikan urutan halaman berdasarkan pilihan user
    pages_order = []
    page_index_map = {}  # Untuk menyimpan mapping nama halaman ke indeks

    def convert_image_to_pdf(image_path, page_info=None):
        """Konversi gambar ke PDF dengan metadata untuk hyperlink"""
        image = Image.open(image_path).convert('RGB')
        img_width, img_height = image.size

        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=(img_width, img_height))
        c.drawImage(image_path, 0, 0, width=img_width, height=img_height)

        # Tambahkan hyperlink dari SVGElement jika ada
        if page_info and page_info.get('layout_type') and page_info.get('option_name'):
            coords = SVGElement.query.filter_by(
                product_id=product_id,
                layout_type=page_info['layout_type'],
                option_name=page_info['option_name']
            ).all()
            for el in coords:
                # Estimasi ukuran berdasarkan nama
                width = len(el.name) * 10  # Estimasi lebar berdasarkan panjang teks
                height = 20  # Tinggi default
                
                c.linkRect(
                    "", el.name,
                    (el.x, el.y, el.x + width, el.y + height),
                    relative=0
                )

        c.save()
        temp_name = f"temp_{len(pages_order)}"
        temp_path = f"temp/{temp_name}.pdf"
        with open(temp_path, 'wb') as f:
            f.write(packet.getvalue())
        return temp_path

    # ===== Tambah Halaman ====
    # Definisikan struktur halaman
    temp_pages = []
    
    # 1. Cover
    cover_path = os.path.join(base_path, "cover", "cover.png")
    if os.path.exists(cover_path):
        page_info = {
            'name': 'cover',
            'type': 'cover'
        }
        temp_pdf = convert_image_to_pdf(cover_path, page_info)
        temp_pages.append(temp_pdf)
        page_index_map['cover'] = len(temp_pages) - 1
    
    # 2. Ring (jika landscape)
    if orientation == "landscape" and ring:
        ring_path = os.path.join(base_path, "rings", f"{ring}.png")
        if os.path.exists(ring_path):
            page_info = {
                'name': 'ring',
                'type': 'ring'
            }
            temp_pdf = convert_image_to_pdf(ring_path, page_info)
            temp_pages.append(temp_pdf)
            page_index_map['ring'] = len(temp_pages) - 1

    # 3. Tab
    tab_path = os.path.join(base_path, "tabs", f"{tab}.png")
    if os.path.exists(tab_path):
        page_info = {
            'name': 'tab',
            'type': 'tab'
        }
        temp_pdf = convert_image_to_pdf(tab_path, page_info)
        temp_pages.append(temp_pdf)
        page_index_map['tab'] = len(temp_pages) - 1

    # 4. Weekly Layout
    weekly_path = os.path.join(base_path, "layouts", f"weekly_{weekly}.png")
    if os.path.exists(weekly_path):
        page_info = {
            'name': f'weekly_{weekly}',
            'type': 'weekly',
            'layout_type': 'weekly',
            'option_name': weekly
        }
        temp_pdf = convert_image_to_pdf(weekly_path, page_info)
        temp_pages.append(temp_pdf)
        page_index_map[f'weekly_{weekly}'] = len(temp_pages) - 1

    # 5. Daily Layout
    if daily and daily != 'none':
        daily_path = os.path.join(base_path, "layouts", f"daily_{daily}.png")
        if os.path.exists(daily_path):
            page_info = {
                'name': f'daily_{daily}',
                'type': 'daily',
                'layout_type': 'daily',
                'option_name': daily
            }
            temp_pdf = convert_image_to_pdf(daily_path, page_info)
            temp_pages.append(temp_pdf)
            page_index_map[f'daily_{daily}'] = len(temp_pages) - 1
        
    # 6. Extra Pages
    for extra in ['icons', 'stickers']:
        extra_path = os.path.join(base_path, extra, f"{extra}.png")
        if os.path.exists(extra_path):
            page_info = {
                'name': f'extra_{extra}',
                'type': 'extra'
            }
            temp_pdf = convert_image_to_pdf(extra_path, page_info)
            temp_pages.append(temp_pdf)
            page_index_map[f'extra_{extra}'] = len(temp_pages) - 1

    # ===== Gabungkan Semua Halaman ====
    merged_path = f"temp/merged_{product_id}.pdf"
    merger = PdfMerger()
    for pdf in temp_pages:
        merger.append(pdf)
    merger.write(merged_path)
    merger.close()

    # ===== Tambahkan Hyperlink dari DB LayoutHyperlink ====
    doc = fitz.open(merged_path)
    hyperlinks = LayoutHyperlink.query.filter_by(layout_type='weekly', layout_name=weekly).all()

    for link in hyperlinks:
        if link.page and link.page <= len(doc):
            page = doc[link.page - 1]
            rect = fitz.Rect(link.x, link.y, link.x + link.width, link.y + link.height)
            if link.destination and link.destination.startswith("page:"):
                try:
                    dest_page = int(link.destination.split(":")[1]) - 1
                    page.insert_link({
                        "kind": fitz.LINK_GOTO,
                        "from": rect,
                        "page": dest_page
                    })
                except:
                    continue
            elif link.destination:
                page.insert_link({
                    "kind": fitz.LINK_URI,
                    "from": rect,
                    "uri": link.destination
                })
    
    # Tambahkan hyperlink antar halaman berdasarkan SVG elements
    # Definisikan mapping nama ke halaman tujuan
    destination_map = {
        # Navigasi ke halaman monthly
        'monthly': page_index_map.get('monthly_january', 0),
        'january': page_index_map.get('monthly_january', 0),
        'february': page_index_map.get('monthly_february', 0),
        'march': page_index_map.get('monthly_march', 0),
        'april': page_index_map.get('monthly_april', 0),
        'may': page_index_map.get('monthly_may', 0),
        'june': page_index_map.get('monthly_june', 0),
        'july': page_index_map.get('monthly_july', 0),
        'august': page_index_map.get('monthly_august', 0),
        'september': page_index_map.get('monthly_september', 0),
        'october': page_index_map.get('monthly_october', 0),
        'november': page_index_map.get('monthly_november', 0),
        'december': page_index_map.get('monthly_december', 0),
        
        # Navigasi ke halaman weekly/daily
        'weekly': page_index_map.get(f'weekly_{weekly}', 0),
        'daily': page_index_map.get(f'daily_{daily}', 0),
        
        # Navigasi ke halaman extras
        'icons': page_index_map.get('extra_icons', 0),
        'stickers': page_index_map.get('extra_stickers', 0),
        
        # Navigasi ke halaman utama
        'cover': page_index_map.get('cover', 0),
        'home': page_index_map.get('cover', 0),
    }

    # Tambahkan hyperlink antar halaman berdasarkan SVG elements
    svg_elements = SVGElement.query.filter_by(product_id=product_id).all()
    for el in svg_elements:
        # Cari halaman yang memiliki elemen ini
        page_index = None
        if el.layout_type == 'weekly':
            page_index = page_index_map.get(f'weekly_{el.option_name}')
        elif el.layout_type == 'daily':
            page_index = page_index_map.get(f'daily_{el.option_name}')
        elif el.layout_type == 'monthly':
            page_index = page_index_map.get(f'monthly_{el.option_name}')
        elif el.layout_type == 'extra':
            page_index = page_index_map.get(f'extra_{el.option_name}')
            
        if page_index is not None:
            # Cari halaman tujuan berdasarkan nama elemen
            dest_name = el.name.lower()
            dest_page = destination_map.get(dest_name)
            
            if dest_page is not None:
                # Estimasi ukuran berdasarkan nama
                width = len(el.name) * 10  # Estimasi lebar berdasarkan panjang teks
                height = 20  # Tinggi default
                
                # Buat hyperlink ke halaman tujuan
                page = doc[page_index]
                rect = fitz.Rect(el.x, el.y, el.x + width, el.y + height)
                page.insert_link({
                    "kind": fitz.LINK_GOTO,
                    "from": rect,
                    "page": dest_page
                })

    # Simpan dokumen dengan hyperlink
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    # ===== Cleanup sementara =====
    os.remove(merged_path)
    for f in temp_pages:
        os.remove(f)

# ========================
# SVG Coordinate Extractor
# ========================
def parse_svg(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        svg = f.read()
    soup = BeautifulSoup(svg, 'xml')
    elements = []

    # Parse text elements
    for text in soup.find_all('text'):
        name = text.string.strip() if text.string else 'unnamed'
        x = float(text.get('x', 0))
        y = float(text.get('y', 0))
        
        # Estimasi ukuran berdasarkan teks dan font
        font_size = float(text.get('font-size', 12).replace('px', ''))
        width = len(name) * (font_size * 0.6)  # Estimasi lebar berdasarkan panjang teks
        height = font_size * 1.2  # Estimasi tinggi berdasarkan ukuran font
        
        elements.append({
            'name': name, 
            'x': x, 
            'y': y - height,  # Sesuaikan y agar rect dimulai dari atas teks
            'width': width,
            'height': height,
            'type': 'text'
        })
    
    # Parse rect elements dengan id
    for rect in soup.find_all('rect'):
        try:
            rect_id = rect.get('id')
            if rect_id:  # Hanya proses rect dengan id
                x = float(rect.get('x', 0))
                y = float(rect.get('y', 0))
                width = float(rect.get('width', 0))
                height = float(rect.get('height', 0))
                
                elements.append({
                    'name': rect_id,
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'type': 'rect'
                })
        except (ValueError, TypeError):
            continue

    return elements

def save_svg_coordinates(product_id, layout_type, option_name, svg_path):
    coords = parse_svg(svg_path)
    for el in coords:
        db.session.add(SVGElement(
            product_id=product_id,
            layout_type=layout_type,
            option_name=option_name,
            name=el['name'],
            x=el['x'],
            y=el['y'],
            width=el.get('width', 50),  # Default width jika tidak ada
            height=el.get('height', 20),  # Default height jika tidak ada
            element_type=el.get('type', 'text')  # Default type adalah text
        ))
    db.session.commit()

# ========================
# PDF Hyperlink Extractor
# ========================
def extract_pdf_links(pdf_path):
    doc = fitz.open(pdf_path)
    results = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        links = page.get_links()
        for link in links:
            if 'from' in link and 'uri' not in link:
                rect = link['from']
                destination = link.get('page')
                dest_str = f"page:{destination + 1}" if isinstance(destination, int) else ''
                results.append({
                    'page': page_num + 1,
                    'x': rect.x0,
                    'y': rect.y0,
                    'width': rect.width,
                    'height': rect.height,
                    'destination': dest_str
                })

    doc.close()
    return results

# ========================
# Generate PDF Preview
# ========================
def generate_preview(pdf_path, output_dir, max_pages=3, dpi=150):
    """Generate preview images from PDF"""
    os.makedirs(output_dir, exist_ok=True)
    preview_paths = []
    
    doc = fitz.open(pdf_path)
    page_count = min(len(doc), max_pages)  # Batasi jumlah halaman preview
    
    for page_num in range(page_count):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))  # Render dengan DPI yang ditentukan
        preview_path = os.path.join(output_dir, f"preview_{page_num+1}.png")
        pix.save(preview_path)
        preview_paths.append(preview_path)
    
    doc.close()
    return preview_paths

# ========================
# Extract Product ID dari Kode Akses
# ========================
def get_product_id_from_code(code):
    try:
        return int(code.split('-')[0])
    except (IndexError, ValueError):
        return None

# ========================
# Etsy Webhook Verification
# ========================
def verify_etsy_signature(signature, payload):
    """Verifikasi signature dari Etsy untuk keamanan webhook"""
    if not signature:
        return False
        
    # Gunakan environment variable untuk secret key
    # Untuk development, gunakan key dummy
    secret = os.environ.get('ETSY_WEBHOOK_SECRET', 'etsy_webhook_secret_key')
    
    # Hitung HMAC dengan SHA-256
    computed_hash = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    # Bandingkan dengan signature dari Etsy
    return hmac.compare_digest(computed_hash, signature)

# ========================
# Email Sender
# ========================
def send_access_code_email(email, access_code):
    """Kirim email dengan kode akses ke pembeli"""
    subject = "Your Loot Pixel Planner Access Code"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #7c3aed; text-align: center;">Thank you for your purchase!</h2>
            <p>Here is your unique access code to build your digital planner:</p>
            <div style="padding: 15px; background-color: #f0f0f0; font-size: 24px; text-align: center; font-family: monospace; border-radius: 5px; margin: 20px 0;">
                {access_code}
            </div>
            <p>Visit <a href="https://lootpixel.com/access" style="color: #7c3aed;">lootpixel.com/access</a> to start building your planner.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #777; text-align: center;">
                This is an automated message. Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    """
    
    msg = Message(subject, recipients=[email])
    msg.html = body
    mail.send(msg)
