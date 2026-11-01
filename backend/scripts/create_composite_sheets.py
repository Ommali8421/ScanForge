"""
Generate composite comparison sheets for:
1. Over-pruning before/after (House & Tour)
2. Poisson vs Delaunay (House & Tour)
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def create_pruning_sheet(name, original_dir, conservative_dir, out_path, title, orig_caption, cons_caption):
    views = ["persp1.png", "persp2.png", "top.png", "side.png"]
    view_labels = ["Perspective View 1", "Perspective View 2", "Top-Down View", "Side / Profile View"]
    
    orig_imgs = [Image.open(original_dir / v) for v in views]
    cons_imgs = [Image.open(conservative_dir / v) for v in views]
    
    tile_w, tile_h = orig_imgs[0].size  # 800x600 typically
    
    header_h = 70
    section_h = 45
    pad = 10
    total_w = tile_w * 4 + pad * 5
    total_h = header_h + (section_h + tile_h + pad) * 2 + pad
    
    canvas = Image.new("RGB", (total_w, total_h), (245, 247, 250))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    
    # Title
    draw.rectangle([(0, 0), (total_w, header_h)], fill=(20, 25, 35))
    draw.text((pad * 2, 15), title, fill=(255, 255, 255), font=font)
    draw.text((pad * 2, 40), "Red: Below-Floor Pruned  |  Orange: Outside-Wall Pruned  |  Grey: Kept Geometry  |  Cyan: Floor Plane  |  Yellow: Wall Planes", fill=(180, 195, 210), font=font)
    
    # Row 1: Original
    y_row1 = header_h + pad
    draw.rectangle([(pad, y_row1), (total_w - pad, y_row1 + section_h)], fill=(230, 235, 242))
    draw.text((pad * 2, y_row1 + 15), orig_caption, fill=(180, 30, 30), font=font)
    
    for i, (img, v_lbl) in enumerate(zip(orig_imgs, view_labels)):
        x = pad + i * (tile_w + pad)
        y = y_row1 + section_h + 5
        canvas.paste(img, (x, y))
        draw.text((x + 10, y + 10), v_lbl, fill=(40, 40, 40), font=font)
        
    # Row 2: Conservative
    y_row2 = y_row1 + section_h + tile_h + pad * 2
    draw.rectangle([(pad, y_row2), (total_w - pad, y_row2 + section_h)], fill=(230, 235, 242))
    draw.text((pad * 2, y_row2 + 15), cons_caption, fill=(20, 140, 60), font=font)
    
    for i, (img, v_lbl) in enumerate(zip(cons_imgs, view_labels)):
        x = pad + i * (tile_w + pad)
        y = y_row2 + section_h + 5
        canvas.paste(img, (x, y))
        draw.text((x + 10, y + 10), v_lbl, fill=(40, 40, 40), font=font)
        
    canvas.save(out_path)
    print(f"Saved: {out_path} ({total_w}x{total_h})")

def create_poisson_sheet(name, del_path, poi_path, out_path, title, del_caption, poi_caption):
    img_del = Image.open(del_path)
    img_poi = Image.open(poi_path)
    w, h = img_del.size
    
    header_h = 70
    pad = 15
    total_w = w * 2 + pad * 3
    total_h = header_h + h + pad * 2
    
    canvas = Image.new("RGB", (total_w, total_h), (245, 247, 250))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    
    draw.rectangle([(0, 0), (total_w, header_h)], fill=(20, 25, 35))
    draw.text((pad * 2, 15), title, fill=(255, 255, 255), font=font)
    
    # Delaunay
    x1 = pad
    y = header_h + pad
    canvas.paste(img_del, (x1, y))
    draw.rectangle([(x1, y), (x1 + w, y + 35)], fill=(30, 40, 55))
    draw.text((x1 + 10, y + 10), del_caption, fill=(255, 255, 255), font=font)
    
    # Poisson
    x2 = x1 + w + pad
    canvas.paste(img_poi, (x2, y))
    draw.rectangle([(x2, y), (x2 + w, y + 35)], fill=(30, 40, 55))
    draw.text((x2 + 10, y + 10), poi_caption, fill=(255, 255, 255), font=font)
    
    canvas.save(out_path)
    print(f"Saved: {out_path} ({total_w}x{total_h})")

def main():
    root = Path("/data/outputs")
    
    # 1. House Pruning Sheet
    create_pruning_sheet(
        "house",
        root / "house_pruning_views",
        root / "house_conservative_views",
        root / "house_overpruning_analysis.png",
        "ScanForge Interior Reconstruction - Over-Pruning Analysis: House Clip (f0e89d25)",
        "BEFORE (Original Phase 2 Over-Pruning): 79,759 faces (22.4%) culled below floor (tabletop picked as floor at height -4.740, slicing lower room).",
        "AFTER (Conservative Envelope Pruning): 0 faces (0.00%) culled below floor (true floor Candidate 0 chosen with 3,163 inliers; camera bbox protected)."
    )
    
    # 2. Tour Pruning Sheet
    create_pruning_sheet(
        "tour",
        root / "tour_pruning_views",
        root / "tour_conservative_views",
        root / "tour_overpruning_analysis.png",
        "ScanForge Interior Reconstruction - Over-Pruning Analysis: Tour Clip (2b7b3bcc)",
        "BEFORE (Original Phase 2 Over-Pruning): 88,914 faces (12.1%) culled outside walls (only 1 wall plane detected; single infinite half-space sliced room).",
        "AFTER (Conservative Envelope Pruning): 0 faces (0.00%) culled outside walls (single-plane wall culling disabled; 1,094 mirror floaters pruned [0.15%])."
    )
    
    # 3. Poisson vs Delaunay - House
    create_poisson_sheet(
        "house",
        root / "comparison" / "house_delaunay.png",
        root / "comparison" / "house_poisson.png",
        root / "house_poisson_vs_delaunay.png",
        "A/B Reconstruction Comparison: Delaunay vs Screened Poisson - House Clip",
        "RECOMMENDED: Delaunay (OpenMVS ReconstructMesh + Plane Regularization) | 272k faces, faithful boundaries, no balloons",
        "OPTIONAL: Screened Poisson (Open3D) | 640k faces, smooth closed manifold, but inflates unobserved regions"
    )
    
    # 4. Poisson vs Delaunay - Tour
    create_poisson_sheet(
        "tour",
        root / "comparison" / "tour_delaunay.png",
        root / "comparison" / "tour_poisson.png",
        root / "tour_poisson_vs_delaunay.png",
        "A/B Reconstruction Comparison: Delaunay vs Screened Poisson - Tour Clip",
        "RECOMMENDED: Delaunay (OpenMVS ReconstructMesh + Plane Regularization) | 631k faces, sharp corners, exact room volume",
        "OPTIONAL: Screened Poisson (Open3D) | 283k faces, massive 3x balloon inflation in unobserved ceiling/doorways"
    )

if __name__ == "__main__":
    main()

