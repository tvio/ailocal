import os
import uuid
import re
from qdrant_client import QdrantClient
from qdrant_client import models
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from docling.document_converter import DocumentConverter

# --- Nastavení ---
SPC_DIR = "/home/dvacek/Hajek_Data_Krabickovani"  # Složka s SPC dokumenty
SPC_COLLECTION = "spc_data"                       # Cílová kolekce pro SPC
SUKL_COLLECTION = "seznam_uhrad_data"             # Původní kolekce (zdroj pravdy pro OTC)
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
QDRANT_URL = "http://localhost:6333"

print("Načítám modely (BGE-M3 a BM25)...")
encoder_dense = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cuda")
encoder_sparse = SparseTextEmbedding(model_name="Qdrant/bm25")
client = QdrantClient(url=QDRANT_URL)

# Vytvoření/přemazání hybridní kolekce SPC
if client.collection_exists(collection_name=SPC_COLLECTION):
    print(f"Mažu původní kolekci '{SPC_COLLECTION}'...")
    client.delete_collection(collection_name=SPC_COLLECTION)

client.create_collection(
    collection_name=SPC_COLLECTION,
    vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
    sparse_vectors_config={"sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=True))}
)
print(f"Nová hybridní kolekce '{SPC_COLLECTION}' připravena.")

# Splittery
headers_to_split_on = [("#", "H1"), ("##", "H2"), ("###", "H3")]
markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=300)
doc_converter = DocumentConverter()

# --- Pomocné funkce ---
def zjisti_otc_ze_sukl_databaze(sukl_kod):
    """
    Vyhledá lék podle SÚKL kódu v kolekci 'seznam_uhrad_data' 
    a ověří, zda má nastaven 'způsob výdeje: V' (OTC).
    """
    if not client.collection_exists(SUKL_COLLECTION):
        return None

    try:
        # Použití BM25 pro přesnou shodu SÚKL kódu
        q_sparse = next(encoder_sparse.query_embed(sukl_kod))
        
        res = client.query_points(
            collection_name=SUKL_COLLECTION,
            query=models.SparseVector(indices=q_sparse.indices.tolist(), values=q_sparse.values.tolist()),
            using="sparse",
            limit=3 
        ).points
        
        for p in res:
            text_zaznamu = p.payload.get("text", "").upper()
            
            # Ověření nalezeného záznamu
            if f"KÓD SÚKL: {sukl_kod}" in text_zaznamu or f"KÓD: {sukl_kod}" in text_zaznamu:
                if "ZPŮSOB VÝDEJE: V" in text_zaznamu:
                    return True
                elif "ZPŮSOB VÝDEJE: R" in text_zaznamu:
                    return False
                    
    except Exception as e:
        print(f"      [CHYBA] Nepodařilo se spojit s DB SÚKL: {e}")
        
    return None

# --- Zpracování souborů ---
print(f"\nZahajuji vytěžování SPC ze složky: {SPC_DIR}")

for root_dir, dirs, files in os.walk(SPC_DIR):
    for filename in files:
        if filename.startswith('.') or filename.startswith('~'):
            continue
            
        file_path = os.path.join(root_dir, filename)
        print(f" -> Zpracovávám: {filename}")
        
        # 1. Extrakce SÚKL kódu z názvu souboru (např. SPC_0254048_PARALEN -> 0254048)
        sukl_kod_match = re.search(r'SPC_0*(\d+)_', filename, re.IGNORECASE)
        sukl_kod = sukl_kod_match.group(1) if sukl_kod_match else None
        
        # 2. Očištění názvu pro model (např. "PARALEN")
        clean_name = re.sub(r'(?i)^SPC_\d+_', '', filename) 
        clean_name = os.path.splitext(clean_name)[0]        
        
        try:
            conv_result = doc_converter.convert(file_path)
            full_md_text = conv_result.document.export_to_markdown()
            
            if not full_md_text.strip():
                continue

            # --- Detekce OTC vs. Rx ---
            is_otc = False
            zdroj_informace = "Neznámý"
            
            # A: Dotaz do SÚKL databáze
            if sukl_kod:
                sukl_vysledek = zjisti_otc_ze_sukl_databaze(sukl_kod)
                if sukl_vysledek is True:
                    is_otc = True
                    zdroj_informace = "Databáze Ceníků SÚKL"
                elif sukl_vysledek is False:
                    is_otc = False
                    zdroj_informace = "Databáze Ceníků SÚKL"
                else:
                    zdroj_informace = "Nenalezeno v SÚKL DB, použit Fallback"
            
            # B: Fallback (regex v textu / známé názvy)
            if zdroj_informace == "Nenalezeno v SÚKL DB, použit Fallback" or not sukl_kod:
                otc_patterns = r'(bez lékařského předpisu|bez předpisu|volně prodej|výdej léčivého přípravku není vázán na předpis)'
                zname_otc_nazvy = ['paralen', 'ibalgin', 'aspirin', 'paracetamol', 'ibuprofen', 'nalgesin', 'panadol', 'acylpyrin']
                
                if re.search(otc_patterns, full_md_text, re.IGNORECASE):
                    is_otc = True
                    zdroj_informace = "Text SPC dokumentu"
                elif any(otc_word in clean_name.lower() for otc_word in zname_otc_nazvy):
                    is_otc = True
                    zdroj_informace = "Bezpečnostní seznam názvů"

            if is_otc:
                print(f"    [INFO] OTC Lék (Volný prodej). Zdroj: {zdroj_informace}")
            else:
                print(f"    [INFO] Rx Lék (Na recept). Zdroj: {zdroj_informace}")

            # --- Uložení do Qdrantu ---
            md_splits = markdown_splitter.split_text(full_md_text)
            chunks = text_splitter.split_documents(md_splits)
            
            file_points = []
            for chunk in chunks:
                h1 = chunk.metadata.get("H1", "")
                h2 = chunk.metadata.get("H2", "")
                h3 = chunk.metadata.get("H3", "")
                kapitola = " -> ".join([h for h in [h1, h2, h3] if h]) or "Obecná sekce"
                
                raw_text = chunk.page_content
                
                text_pro_vektor = (
                    f"Léčivý přípravek (Dokument): {clean_name}\n"
                    f"Sekce SPC dokumentu: {kapitola}\n"
                    f"Volně prodejný lék: {'Ano' if is_otc else 'Ne'}\n"
                    f"Obsah této sekce:\n{raw_text}"
                )
                
                vec_dense = encoder_dense.encode(text_pro_vektor).tolist()
                vec_sparse = next(encoder_sparse.embed([text_pro_vektor]))
                
                payload = {
                    "text": raw_text,
                    "source": filename,
                    "drug_name": clean_name,
                    "chapter": kapitola,
                    "is_otc": is_otc
                }
                
                file_points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": vec_dense,
                        "sparse": models.SparseVector(indices=vec_sparse.indices.tolist(), values=vec_sparse.values.tolist())
                    },
                    payload=payload
                ))
            
            batch_size = 100
            for i in range(0, len(file_points), batch_size):
                client.upsert(collection_name=SPC_COLLECTION, points=file_points[i:i + batch_size])
            print(f"    [OK] Uloženo {len(file_points)} vektorů.")
            
        except Exception as e:
            print(f"    [CHYBA] Selhalo u {filename}: {e}")

print("\nZpracování dokončeno. Všechna data nahrána do Qdrantu.")