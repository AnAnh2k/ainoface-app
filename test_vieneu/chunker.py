import re
from typing import List

def split_tts_chunks(text:str, min_words: int = 4, max_words:int =25) -> List[str]:
    if not text:
        return []
    
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    sentences = re.findall(r"[^.!?。！？]+[.!?。！？]*|[^.!?。！？]+$", text)
    chunks: List[str] = []
    buffer = ""
    for raw_sentence in sentences:
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        
        candidate = sentence if not buffer else f"{buffer} {sentence}"
        candidate_words = len(candidate.split())
        
        if not buffer:
            buffer = sentence
            continue
        if candidate_words <= max_words:
            buffer =  candidate
            continue
        if len(buffer.split()) < min_words:
            buffer = candidate
            continue
        
        chunks.append(buffer)
        buffer = sentence
    if buffer:
        chunks.append(buffer)
    return chunks