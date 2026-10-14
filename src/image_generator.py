from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import textwrap
import os
import subprocess

def generate_image(text, theme="GENERAL", output_path="quote.png", bg_image_path="clound.jpg", seed=None, blend_mode="screen", text_opacity=0.8):
    # Image size
    width, height = 1080, 1080
    
    # Load background image or fallback
    if os.path.exists(bg_image_path):
        bg = Image.open(bg_image_path)
        bg_ratio = bg.width / bg.height
        target_ratio = width / height
        if bg_ratio > target_ratio:
            new_width = int(target_ratio * bg.height)
            left = (bg.width - new_width) / 2
            bg = bg.crop((left, 0, left + new_width, bg.height))
        else:
            new_height = int(bg.width / target_ratio)
            top = (bg.height - new_height) / 2
            bg = bg.crop((0, top, bg.width, top + new_height))
        base = bg.resize((width, height), Image.Resampling.LANCZOS)
        
        # Add a dark overlay
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 110))
        base = base.convert('RGBA')
        base = Image.alpha_composite(base, overlay).convert('RGB')
    else:
        base = Image.new('RGB', (width, height), (30, 30, 30))

    draw = ImageDraw.Draw(base)
    
# Fonts
    def resolve_font(name):
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", name],
                                 capture_output=True, text=True).stdout.strip()
            return out if out and os.path.exists(out) else None
        except Exception:
            return None

    font_path_main = resolve_font("JetBrains Mono:style=ExtraLight") or "/nix/store/bklz49kjsxvpbargjdpphc6gwwn67vmx-nerd-fonts-jetbrains-mono-3.4.0+2.304/share/fonts/truetype/NerdFonts/JetBrainsMono/JetBrainsMonoNerdFont-ExtraLight.ttf"
    font_path_light = resolve_font("JetBrains Mono:style=Thin") or "/nix/store/bklz49kjsxvpbargjdpphc6gwwn67vmx-nerd-fonts-jetbrains-mono-3.4.0+2.304/share/fonts/truetype/NerdFonts/JetBrainsMono/JetBrainsMonoNerdFont-Thin.ttf"

    if not os.path.exists(font_path_main):
        font_main = ImageFont.load_default()
        font_tiny = ImageFont.load_default()
    else:
        font_tiny = ImageFont.truetype(font_path_light, 16) # Ultra small
        # Adaptive main font: bump size until text nearly fills the canvas.
        for size in (24, 28, 32, 36, 40, 44, 48):
            font_main = ImageFont.truetype(font_path_main, size)
            wrapped = textwrap.fill(text, width=30).split('\n')
            total = sum(draw.textbbox((0, 0), l, font=font_main)[3] for l in wrapped) + (len(wrapped) - 1) * 18
            if total > height * 0.35:
                break

    # Wrap and Draw Main Text
    wrapped_text = textwrap.fill(text, width=30)
    lines = wrapped_text.split('\n')
    line_spacing = 18
    total_text_height = sum(draw.textbbox((0, 0), line, font=font_main)[3] for line in lines) + (len(lines) - 1) * line_spacing

    # Draw onto a separate layer so the text can be faded/blended like a Photoshop overlay.
    text_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)

    current_y = (height - total_text_height) / 2
    for line in lines:
        line_bbox = td.textbbox((0, 0), line, font=font_main)
        line_width = line_bbox[2] - line_bbox[0]
        td.text(((width - line_width) / 2 + 2, current_y + 2), line, font=font_main, fill=(30, 30, 30, 160))
        td.text(((width - line_width) / 2, current_y), line, font=font_main, fill=(255, 255, 255, 255))
        current_y += line_bbox[3] - line_bbox[1] + line_spacing

    # Combined Ultra-Small Info Row
    footer_y = height - 60
    display_seed = (seed[:8] + "...") if seed and len(seed) > 12 else (seed or "N/A")
    info_text = f"THEME: {theme.lower()}  |  SEED: {display_seed}  |  ENGINE: shitty v3"
    i_bbox = td.textbbox((0, 0), info_text, font=font_tiny)
    i_width = i_bbox[2] - i_bbox[0]
    td.text(((width - i_width) / 2, footer_y), info_text, font=font_tiny, fill=(255, 255, 255, 90))

    # Soft glow: blurred, dimmed copy behind the text.
    glow = text_layer.filter(ImageFilter.GaussianBlur(8)).point(lambda p: int(p * 0.6))
    layer_full = Image.alpha_composite(glow, text_layer)

    if blend_mode == "normal":
        # Photoshop "Normal" layer at reduced opacity.
        faded = layer_full.copy()
        faded.putalpha(faded.getchannel('A').point(lambda a: int(a * text_opacity)))
        base = Image.alpha_composite(base.convert('RGBA'), faded).convert('RGB')
    else:
        # Photoshop "Screen" blend: text adds light to the scene, ghost-like.
        text_flat = Image.alpha_composite(Image.new('RGBA', (width, height), (0, 0, 0, 255)), layer_full).convert('RGB')
        dim = Image.new('RGB', (width, height), (int(255 * text_opacity),) * 3)
        faded = ImageChops.multiply(text_flat, dim)
        base = ImageChops.screen(base.convert('RGB'), faded)

    base.save(output_path)
    print(f"Ultra-minimalist image saved to: {output_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        text = sys.argv[1]
        theme = sys.argv[2] if len(sys.argv) > 2 else "GENERAL"
        output = sys.argv[3] if len(sys.argv) > 3 else "quote.png"
        seed = sys.argv[4] if len(sys.argv) > 4 else None
        generate_image(text, theme=theme, output_path=output, seed=seed)
