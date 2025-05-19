#!/usr/bin/env python3
"""
LightKeyia - Standalone Desktop Version (Optimized)
--------------------------------------
A tool to analyze images with Ollama and generate keywords in XMP files.
Compatible with standard and RAW formats.
"""

import os
import sys
import tkinter as tk
import argparse
from config import VERSION, logger
from image_processor import ImageProcessor
from gui import ImageProcessorGUI
from docker_manager import DockerManager

def parse_arguments():
    parser = argparse.ArgumentParser(description=f"LightKeyia v{VERSION} - Image analysis with Ollama")
    parser.add_argument("--directory", "-d", help="Directory to process")
    parser.add_argument("--model", "-m", default="gemma3:4b", help="Ollama model to use")
    parser.add_argument("--ollama-url", default="http://host.docker.internal:11434", help="Ollama API URL")
    parser.add_argument("--ollama-urls", help="Comma-separated list of Ollama API URLs")
    parser.add_argument("--recursive", "-r", action="store_true", help="Process subdirectories")
    parser.add_argument("--force", "-f", action="store_true", help="Force processing (ignore cache)")
    parser.add_argument("--threads", "-t", type=int, default=4, help="Number of threads")
    parser.add_argument("--batch-size", "-b", type=int, default=5, help="Batch size")
    parser.add_argument("--pause", "-p", type=int, default=5, help="Pause between batches (seconds)")
    parser.add_argument("--temperature", type=float, default=0.5, help="Model temperature")
    parser.add_argument("--no-gui", action="store_true", help="Run in command-line mode")
    parser.add_argument("--skip-chat-api", action="store_true", help="Skip chat API and use generate API only")
    parser.add_argument("--timeout", type=int, default=300, help="Request timeout in seconds")
    parser.add_argument("--load-balancing", default="round_robin", choices=["round_robin", "least_busy", "fastest", "random"], help="Load balancing strategy")
    parser.add_argument("--create-containers", action="store_true", help="Create Docker containers")
    parser.add_argument("--container-count", type=int, default=3, help="Number of containers to create")
    parser.add_argument("--container-base-name", default="ollama", help="Base name for containers")
    parser.add_argument("--container-start-port", type=int, default=11434, help="Starting port for containers")
    parser.add_argument("--pull-model", action="store_true", help="Pull model to all containers")
    return parser.parse_args()

def run_cli(args):
    logger.info(f"Starting LightKeyia v{VERSION} in CLI mode")
    
    # Create Docker containers if requested
    if args.create_containers:
        docker_manager = DockerManager()
        if not docker_manager.docker_available:
            logger.error("Docker is not available on this system")
            sys.exit(1)
        
        logger.info(f"Creating {args.container_count} Docker containers...")
        results = docker_manager.create_multiple_containers(
            args.container_base_name,
            args.container_start_port,
            args.container_count
        )
        
        # Log results
        for result in results:
            status = "created successfully" if result["success"] else "creation failed"
            logger.info(f"Container {result['name']} (port {result['port']}): {status}")
            if not result["success"]:
                logger.error(f"  Error: {result['message']}")
        
        # Update Ollama URLs
        if args.ollama_urls:
            ollama_urls = args.ollama_urls.split(',')
        else:
            ollama_urls = []
            for i in range(args.container_count):
                port = args.container_start_port + i
                ollama_urls.append(f"http://localhost:{port}")
            args.ollama_urls = ','.join(ollama_urls)
        
        # Pull model if requested
        if args.pull_model:
            logger.info(f"Pulling model {args.model} to all containers...")
            for url in ollama_urls:
                success, message = docker_manager.pull_model(url, args.model)
                if success:
                    logger.info(f"Model {args.model} pulled successfully to {url}")
                else:
                    logger.error(f"Error pulling model {args.model} to {url}: {message}")
    
    if not args.directory:
        logger.error("No directory specified. Use --directory or -d to specify a directory.")
        sys.exit(1)
    
    if not os.path.isdir(args.directory):
        logger.error(f"Directory not found: {args.directory}")
        sys.exit(1)
    
    # Prepare Ollama URLs
    ollama_urls = args.ollama_urls.split(',') if args.ollama_urls else [args.ollama_url]
    
    processor = ImageProcessor(
        model=args.model,
        ollama_urls=ollama_urls,
        load_balancing_strategy=args.load_balancing,
        threads=args.threads,
        force_processing=args.force,
        batch_size=args.batch_size,
        pause_between_batches=args.pause,
        temperature=args.temperature,
        skip_chat_api=args.skip_chat_api,
        request_timeout=args.timeout
    )
    
    logger.info(f"Processing directory: {args.directory}")
    logger.info(f"Using model: {args.model}")
    logger.info(f"Recursive: {args.recursive}")
    logger.info(f"Request timeout: {args.timeout} seconds")
    logger.info(f"Ollama URLs: {ollama_urls}")
    logger.info(f"Load balancing strategy: {args.load_balancing}")
    
    processor.process_directory(args.directory, recursive=args.recursive)
    
    logger.info("Processing complete")

def run_gui():
    logger.info(f"Starting LightKeyia v{VERSION} in GUI mode")
    root = tk.Tk()
    app = ImageProcessorGUI(root)
    root.mainloop()

def main():
    args = parse_arguments()
    
    if args.no_gui:
        run_cli(args)
    else:
        run_gui()

if __name__ == "__main__":
    main()
