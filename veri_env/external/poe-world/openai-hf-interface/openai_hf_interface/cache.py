# Ref: https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain/cache.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.sql.expression import func

from sqlalchemy import Column, Integer, String, create_engine, select, ARRAY, Float
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import Session

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base


class BaseCache(ABC):
    """Base interface for cache."""

    @abstractmethod
    def lookup(self, prompt: str, llm_string: str):
        """Look up based on prompt and llm_string."""

    @abstractmethod
    def update(self, prompt: str, llm_string: str, return_val):
        """Update cache based on prompt and llm_string."""


class InMemoryCache(BaseCache):
    """Cache that stores things in memory."""

    def __init__(self) -> None:
        """Initialize with empty cache."""
        self._cache = {}

    def lookup(self, prompt: str, llm_string: str, temperature: float, max_tokens: int, stop, seed):
        """Look up based on prompt and llm_string."""
        if not isinstance(stop, str): stop = "|".join(stop)
        return self._cache.get((prompt, llm_string, temperature, max_tokens, stop, seed), None)

    def update(self, prompt: str, llm_string: str, return_val, temperature: float, max_tokens: int, stop, seed) -> None:
        """Update cache based on prompt and llm_string."""
        if not isinstance(stop, str): stop = "|".join(stop)
        self._cache[(prompt, llm_string, temperature, max_tokens, stop, seed)] = return_val


Base = declarative_base()
class FullLLMCache(Base):  # type: ignore
    """SQLite table for full LLM Cache (all generations)."""

    __tablename__ = "full_llm_cache"
    idx = Column(Integer, primary_key=True)
    prompt = Column(String, primary_key=True)
    llm = Column(String, primary_key=True)
    temperature = Column(Float, primary_key=True)
    max_tokens = Column(Integer, primary_key=True)
    stop = Column(String, primary_key=True)
    seed = Column(Integer, primary_key=True)
    response = Column(String)
    

class SQLAlchemyCache(BaseCache):
    """Cache that uses SQAlchemy as a backend."""

    def __init__(self, engine: Engine, load_engine: Engine = None, cache_schema: Any = FullLLMCache):
        """Initialize by creating all tables."""
        self.engine = engine
        self.load_engine = load_engine
        self.cache_schema = cache_schema
        self.cache_schema.metadata.create_all(self.engine)

        if load_engine is not None:
            self.cache_schema.metadata.create_all(load_engine)
            with Session(load_engine) as session:
                load_data = session.query(FullLLMCache).all()
            load_data_dicts = []
            for item in load_data:
                item_dict = item.__dict__
                item_dict.pop('_sa_instance_state')
                load_data_dicts.append(item_dict)
            with Session(engine) as session:
                batch_size = 999
                for i in range(0, len(load_data_dicts), batch_size):
                    insert_stmt = insert(FullLLMCache).values(load_data_dicts[i:i+batch_size])
                    session.execute(insert_stmt)
                session.commit()

    def read_all(self):
        stmt = (
            select(self.cache_schema.response,
                self.cache_schema.idx)
        )
        with Session(self.engine) as session:
            generations = [row for row in session.execute(stmt)]
            generations.sort(key=lambda x: x[1])
            generations = [row[0] for row in generations]
        return generations

    def lookup(self, prompt: str, llm_string: str, temperature: float, max_tokens: int, stop, seed):
        """Look up based on prompt and llm_string."""
        if not isinstance(stop, str): stop = "|".join(stop)
        stmt = (
            select(self.cache_schema.response,
                self.cache_schema.idx)
            .where(self.cache_schema.prompt == prompt)
            .where(self.cache_schema.llm == llm_string)
            .where(self.cache_schema.temperature == temperature)
            .where(self.cache_schema.max_tokens == max_tokens)
            .where(self.cache_schema.stop == stop)
            .where(self.cache_schema.seed == seed)
            .order_by(self.cache_schema.idx)
        )
        with Session(self.engine) as session:
            generations = [row for row in session.execute(stmt)]
            generations.sort(key=lambda x: x[1])
            generations = [row[0] for row in generations]
            
            if len(generations) > 0:
                return generations
        return None

    def n_entries(self, prompt: str, llm_string: str, temperature: float, max_tokens: int, stop, seed, session=None):
        """Look up based on prompt and llm_string."""
        if not isinstance(stop, str): stop = "|".join(stop)
        stmt = (
            select(func.max(self.cache_schema.idx))
            .where(self.cache_schema.prompt == prompt)
            .where(self.cache_schema.llm == llm_string)
            .where(self.cache_schema.temperature == temperature)
            .where(self.cache_schema.max_tokens == max_tokens)
            .where(self.cache_schema.stop == stop)
            .where(self.cache_schema.seed == seed)
        )
        if session is None:
            with Session(self.engine) as session:
                generations = list(session.execute(stmt))
                if len(generations) > 0:
                    assert len(generations) == 1
                    g = generations[0][0]
                    if g is None: return 0
                    return g+1
        else:
            generations = list(session.execute(stmt))
            if len(generations) > 0:
                assert len(generations) == 1
                g = generations[0][0]
                if g is None: return 0
                return g+1
                    
        return 0

    def update(self, prompt: str, llm_string: str, return_val, temperature: float, max_tokens: int, stop, seed) -> None:
        if not isinstance(stop, str): stop = "|".join(stop)
        for i, generation in enumerate(return_val):
            item = self.cache_schema(
                prompt=prompt, llm=llm_string, response=generation, idx=i,
                temperature=temperature, max_tokens=max_tokens, stop=stop, seed=seed
            )
            with Session(self.engine) as session, session.begin():
                session.merge(item)
                session.commit()
                
    def extend(self, prompt: str, n_existing: int, llm_string: str, return_val, temperature: float, max_tokens: int, stop, seed) -> None:
        if not isinstance(stop, str): stop = "|".join(stop)
        for i, generation in enumerate(return_val):
            item = self.cache_schema(
                prompt=prompt, llm=llm_string, response=generation, idx=i+n_existing,
                temperature=temperature, max_tokens=max_tokens, stop=stop, seed=seed
            )
            with Session(self.engine) as session, session.begin():
                session.merge(item)
                session.commit()

    def dump_to_disk(self):
        if self.load_engine is None:
            print('No load engine -- everything has been saved to disk. Returning...')
            return
        with Session(self.engine) as session:
            data = session.query(FullLLMCache).all()
        data_dicts = []
        for item in data:
            item_dict = item.__dict__
            item_dict.pop('_sa_instance_state')
            data_dicts.append(item_dict)
        with Session(self.load_engine) as session:
            batch_size = 999
            for i in range(0, len(data_dicts), batch_size):
                insert_stmt = insert(FullLLMCache).values(data_dicts[i:i+batch_size])
                do_update_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=[
                        'idx', 
                        'prompt', 
                        'llm',
                        'temperature',
                        'max_tokens',
                        'stop',
                        'seed'],  # Assuming these are the composite primary keys
                    set_=dict(idx = insert_stmt.excluded.idx, 
                            prompt = insert_stmt.excluded.prompt, 
                            llm = insert_stmt.excluded.llm, 
                            temperature = insert_stmt.excluded.temperature, 
                            max_tokens = insert_stmt.excluded.max_tokens, 
                            stop = insert_stmt.excluded.stop,
                            seed = insert_stmt.excluded.seed,
                            response = insert_stmt.excluded.response)
                )
                session.execute(do_update_stmt)
            session.commit()

class SQLiteCache(SQLAlchemyCache):
    """Cache that uses SQLite as a backend."""

    def __init__(self, database_path: str = "completions.db", to_memory=False):
        """Initialize by creating the engine and all tables."""
        if to_memory:
            engine = create_engine(f"sqlite:///:memory:")
            load_engine = create_engine(f"sqlite:///{database_path}") 
        else:
            engine = create_engine(f"sqlite:///{database_path}")
            load_engine = None
        super().__init__(engine, load_engine)
