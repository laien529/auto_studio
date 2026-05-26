#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ng_asset_tagger.tagger import tag_assets, write_reports
from ng_autopilot.content_generator import generate_ollama, save_content
from ng_autopilot.image_matcher import match_images
from ng_autopilot.renderer import render_html_files, export_png_with_playwright
from ng_autopilot.video import make_srt, make_video

def main():
    parser = argparse.ArgumentParser(description="Auto Studio - Integrated Master Pipeline Script")
    
    # Common arguments
    parser.add_argument("--name", default="project", help="Project name used for output filenames and directories.")
    
    # Tagging stage arguments
    parser.add_argument("--skip-tagging", action="store_true", help="Skip the asset tagging stage.")
    parser.add_argument("--inbox", default="assets/inbox", help="Directory containing raw incoming assets.")
    parser.add_argument("--library", default="assets/library", help="Directory where processed library assets are saved.")
    parser.add_argument("--brand", default=None, help="Car brand for tagging.")
    parser.add_argument("--model", default=None, help="Car model for tagging.")
    parser.add_argument("--series", default=None, help="Car series for tagging.")
    parser.add_argument("--move", action="store_true", help="Move assets instead of copying them during tagging.")
    parser.add_argument("--vision", action="store_true", help="Use vision LLM model for tagging instead of keyword heuristics.")
    parser.add_argument("--vision-model", default=None, help="Vision LLM model name to use for asset tagging. If not specified, dynamically resolved from settings.json.")
    
    # Generation stage arguments
    parser.add_argument("--skip-generation", action="store_true", help="Skip the HTML/Image/Video generation stage.")
    parser.add_argument("--content", default=None, help="Path to an existing content JSON file. If not provided, we will generate it on the fly.")
    parser.add_argument("--topic", default=None, help="Topic for LLM content generation (required if --content is not provided).")
    parser.add_argument("--column", default="新车档案", help="Column style name for LLM content generation.")
    parser.add_argument("--angle", default=None, help="Angle/hook for LLM content generation copywriting.")
    parser.add_argument("--llm-model", default=None, help="LLM model name to use for content generation. If not specified, dynamically resolved from config/settings.json based on provider.")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "openai"], help="LLM provider for content generation.")
    parser.add_argument("--scale-factor", type=int, default=2, help="Device scale factor for Playwright rendering (1 for standard, 2 for Retina 2K, 3 for 3K).")
    
    args = parser.parse_args()
    
    if not args.llm_model:
        try:
            settings_path = ROOT / "config" / "settings.json"
            if settings_path.exists():
                settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                if args.provider == "ollama":
                    args.llm_model = settings_data.get("default_model_ollama", "qwen2.5vl")
                else:
                    args.llm_model = settings_data.get("default_model_openai", "gpt-4.1-mini")
        except Exception:
            pass
        if not args.llm_model:
            args.llm_model = "qwen2.5vl" if args.provider == "ollama" else "gpt-4.1-mini"

    # Resolve default vision model
    if not args.vision_model:
        try:
            settings_path = ROOT / "config" / "settings.json"
            if settings_path.exists():
                settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                args.vision_model = settings_data.get("default_model_vision")
        except Exception:
            pass
        if not args.vision_model:
            args.vision_model = args.llm_model or "qwen2.5vl"
    
    # Validate arguments
    if not args.skip_generation and not args.content:
        if not args.topic:
            parser.error("Either --content (existing JSON path) or --topic (to generate content on the fly) must be specified unless --skip-generation is specified.")
        
    print("=" * 60)
    print("AUTO STUDIO INTEGRATED MASTER PIPELINE")
    print("=" * 60)
    
    # -------------------------------------------------------------
    # Stage 1: Asset Tagging
    # -------------------------------------------------------------
    if not args.skip_tagging:
        print("\n>>> Stage 1: Tagging Assets...")
        inbox_path = ROOT / args.inbox
        library_path = ROOT / args.library
        
        print(f"  Inbox:   {inbox_path}")
        print(f"  Library: {library_path}")
        
        records = tag_assets(
            root=ROOT,
            inbox=inbox_path,
            library=library_path,
            brand=args.brand,
            model=args.model,
            series=args.series,
            move=args.move,
            use_vision=args.vision,
            vision_model=args.vision_model,
        )
        reports = write_reports(records, ROOT / "outputs" / "reports", args.name)
        print(f"  DONE: Tagged {len(records)} assets.")
        for k, v in reports.items():
            print(f"  - {k}: {v}")
    else:
        print("\n>>> Stage 1: Tagging Assets [SKIPPED]")
        
    # -------------------------------------------------------------
    # Stage 2: HTML/Image/Video Generation
    # -------------------------------------------------------------
    if not args.skip_generation:
        print("\n>>> Stage 2: Generating Content & Video...")
        
        # Step 2a: Obtain Content JSON data (Load existing or generate on the fly)
        if args.content:
            content_path = Path(args.content)
            if not content_path.is_absolute():
                content_path = ROOT / content_path
            
            print(f"  Loading existing content JSON: {content_path}")
            if not content_path.exists():
                print(f"  Error: Content file not found at {content_path}")
                sys.exit(1)
            data = json.loads(content_path.read_text(encoding="utf-8"))
        else:
            print(f"  Generating content on the fly using {args.provider.upper()}...")
            print(f"    Topic:  {args.topic}")
            print(f"    Column: {args.column}")
            print(f"    Angle:  {args.angle or 'Default'}")
            print(f"    Model:  {args.llm_model}")
            
            if args.provider == "ollama":
                try:
                    data = generate_ollama(ROOT, args.topic, args.column, args.angle or "", model=args.llm_model)
                except Exception as e:
                    print(f"  Error generating content via Ollama: {e}")
                    sys.exit(1)
            else:
                try:
                    from ng_autopilot.content_generator import generate_openai
                    data = generate_openai(ROOT, args.topic, args.column, args.angle or "", model=args.llm_model)
                except Exception as e:
                    print(f"  Error generating content via OpenAI: {e}")
                    sys.exit(1)
            
            content_path = save_content(ROOT, data, args.name)
            print(f"  DONE: Content generated and saved to {content_path}")
            
        library_path = ROOT / args.library
        print(f"  Assets Root:  {library_path}")
        
        print("  Matching assets with content...")
        matched = match_images(
            content=data,
            assets_root=library_path,
            out_assets=ROOT / "outputs" / "matched_assets" / args.name,
            csv_path=ROOT / "outputs" / "content" / f"{args.name}_canva.csv"
        )
        
        print("  Rendering HTML files...")
        html_dir = render_html_files(ROOT, data, matched["rows"], args.name)
        
        print("  Exporting PNG images using Playwright...")
        png_dir = ROOT / "outputs" / "images" / args.name
        export_png_with_playwright(html_dir, png_dir, device_scale_factor=args.scale_factor)
        
        print("  Creating subtitles (SRT)...")
        srt_path = ROOT / "outputs" / "video" / f"{args.name}.srt"
        make_srt(data.get("douyin", {}).get("subtitles", []), srt_path)
        
        print("  Rendering video...")
        mp4_path = ROOT / "outputs" / "video" / f"{args.name}.mp4"
        try:
            make_video(png_dir, mp4_path)
            print(f"  DONE: Video saved to {mp4_path}")
        except Exception as e:
            print("  Video generation SKIPPED (ffmpeg required). Error:", e)
            
        print("  images:", png_dir)
    else:
        print("\n>>> Stage 2: Generating Content & Video [SKIPPED]")
        
    print("\n" + "=" * 60)
    print("PIPELINE EXECUTION COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()
