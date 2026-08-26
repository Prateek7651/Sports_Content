"""
Seeds ChromaDB with stable/historical sports facts (records, all-time stats, rules).
Run this once before using the app: `python seed_chroma.py`

This is a STARTER set. Expand data/knowledge_base.py with more facts per sport
to improve retrieval quality — this is manual curation work, not automatic.
"""

import chromadb
from chromadb.utils import embedding_functions
from core.retrieval import CHROMA_PATH, COLLECTION_NAME

SEED_FACTS = [
    {"sport": "Cricket", "text": "Sachin Tendulkar holds the record for most international centuries with 100 (51 Test, 49 ODI)."},
    {"sport": "Cricket", "text": "Virat Kohli has the most ODI centuries by any batsman, surpassing Sachin Tendulkar's record of 49 in 2023."},
    {"sport": "Cricket", "text": "The fastest recorded delivery in cricket history is 161.3 km/h, bowled by Shoaib Akhtar in 2003."},
    {"sport": "Cricket", "text": "India won the ICC Cricket World Cup in 1983, 2011, and reached the final in 2023, losing to Australia."},
    {"sport": "Cricket", "text": "Muttiah Muralitharan holds the record for most Test wickets with 800."},
    {"sport": "Football", "text": "Cristiano Ronaldo is the all-time top scorer in men's international football with over 130 goals."},
    {"sport": "Football", "text": "Lionel Messi has won a record 8 Ballon d'Or awards."},
    {"sport": "Football", "text": "Brazil has won the FIFA World Cup a record 5 times: 1958, 1962, 1970, 1994, and 2002."},
    {"sport": "Football", "text": "Argentina won the 2022 FIFA World Cup in Qatar, defeating France on penalties."},
    {"sport": "Football", "text": "The offside rule requires an attacking player to have at least two defenders (including the goalkeeper) between them and the goal line when the ball is played, unless level with the second-last defender."},
    {"sport": "Tennis", "text": "Novak Djokovic holds the record for most Grand Slam men's singles titles with 24."},
    {"sport": "Tennis", "text": "Serena Williams won 23 Grand Slam singles titles, the most in the Open Era."},
    {"sport": "Tennis", "text": "The four Grand Slam tournaments are the Australian Open, French Open (Roland Garros), Wimbledon, and the US Open."},
    {"sport": "Tennis", "text": "A tennis match is won by winning the majority of sets; men's Grand Slam finals are best-of-five sets."},
    {"sport": "Badminton", "text": "PV Sindhu is the first Indian woman to win an Olympic silver medal in badminton (Rio 2016)."},
    {"sport": "Badminton", "text": "A badminton match is played to 21 points per game, best of three games, win by at least 2 points."},
    {"sport": "Badminton", "text": "Lin Dan is one of only two male players to complete the 'Super Grand Slam' by winning all nine major titles."},
    {"sport": "Basketball", "text": "Kareem Abdul-Jabbar was the NBA's all-time leading scorer until Lebron James surpassed his record in 2023."},
    {"sport": "Basketball", "text": "The Boston Celtics hold the record for most NBA championships with 18 titles."},
    {"sport": "Basketball", "text": "A standard NBA game consists of four 12-minute quarters."},
]


def main():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)

    ids = [f"seed_{i}" for i in range(len(SEED_FACTS))]
    documents = [f["text"] for f in SEED_FACTS]
    metadatas = [{"sport": f["sport"]} for f in SEED_FACTS]

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Seeded {len(SEED_FACTS)} facts into ChromaDB at {CHROMA_PATH}")


if __name__ == "__main__":
    main()
