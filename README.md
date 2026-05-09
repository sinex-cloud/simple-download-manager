# Simple Download Manager

A lightweight Python-based download manager with GUI support and download history tracking.

The project was created to explore file downloading, request handling, local file management, and basic desktop application structure using Python.

---

## Features

- Download files from direct URLs
- GUI-based interaction
- Download history tracking
- File metadata handling
- Lightweight project structure

---

## Technologies Used

- Python

---

## Project Structure

```text
simple-download-manager/
│
├── downloader.py
├── gui.py
├── history.py
├── metadata.py
├── main.py
├── download_history.json
├── requirements.txt
└── README.md
```

---

## Setup

Clone the repository:

```bash
git clone https://github.com/sinex-cloud/simple-download-manager.git
cd simple-download-manager
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python main.py
```

---

## Notes

- The `downloads/` folder is generated locally during runtime
- Download history is stored in `download_history.json`

---

## Future Improvements

- Multi-threaded downloads
- Progress tracking improvements
- Pause and resume support
- Better GUI enhancements

---
 
## Disclaimer

This project was developed for educational purposes.
