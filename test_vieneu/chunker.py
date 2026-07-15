import re
from typing import List

def split_tts_chunks(text:str, min_words: int = 6, max_words:int = 25) -> List[str]:
    if not text:
        return []
    
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    sentences = re.findall(r"[^.!?。！？]+[.!?。！？]*|[^.!?。！？]+$", text)
    chunks: List[str] = []
    current_chunk = []
    current_words = 0
    
    for raw_sentence in sentences:
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        
        words = sentence.split()
        word_count = len(words)
        if word_count == 0:
            continue
            
        if current_chunk and (current_words + word_count > max_words) and (current_words >= min_words):
            chunks.append(" ".join(current_chunk))
            current_chunk = words
            current_words = word_count
        else:
            current_chunk.extend(words)
            current_words += word_count
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    # Gộp chunk cuối nếu quá ngắn
    if len(chunks) > 1:
        last_chunk_words = len(chunks[-1].split())
        if last_chunk_words < min_words:
            last = chunks.pop()
            chunks[-1] = chunks[-1] + " " + last
            
    return chunks