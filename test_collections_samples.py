import os
import pytest
import uuid
from app.models.schemas import (
    Collection, CollectionType, BeatAsset, SampleAsset, 
    SampleType, AssetDataType, AssetType
)
from app.core.state_manager import StateManager
from tinydb import TinyDB

def test_schemas_collection_id():
    # Test unassigned (None by default)
    beat = BeatAsset(name="Test Beat", path="/fake/path/beat")
    assert beat.collection_id is None
    
    sample = SampleAsset(name="Test Sample", path="/fake/path/sample.wav")
    assert sample.collection_id is None

def test_collection_linking():
    col_id = str(uuid.uuid4())[:8]
    collection = Collection(id=col_id, name="Test Pack", type=CollectionType.SAMPLE)
    
    sample = SampleAsset(
        name="Loop 1", 
        path="/fake/path/loop1.wav", 
        collection_id=collection.id,
        sample_type=SampleType.LOOP
    )
    assert sample.collection_id == collection.id
    assert sample.sample_type == SampleType.LOOP

def test_state_manager_collections(tmp_path):
    db_path = os.path.join(tmp_path, "test_state.json")
    sm = StateManager(str(db_path))
    
    # Add collection
    col = Collection(name="My Album", type=CollectionType.BEAT)
    sm.add_collection(col.dict())
    
    # Get collections
    cols = sm.get_collections()
    assert len(cols) == 1
    assert cols[0]['name'] == "My Album"
    assert cols[0]['type'] == CollectionType.BEAT
    
    # Filter by type
    sample_cols = sm.get_collections_by_type(CollectionType.SAMPLE)
    assert len(sample_cols) == 0
    
    beat_cols = sm.get_collections_by_type(CollectionType.BEAT)
    assert len(beat_cols) == 1
    assert beat_cols[0]['id'] == col.id

def test_state_manager_samples(tmp_path):
    db_path = os.path.join(tmp_path, "test_state.json")
    sm = StateManager(str(db_path))
    
    sample = SampleAsset(
        name="Snare", 
        path="/path/to/snare.wav", 
        sample_type=SampleType.ONE_SHOT
    )
    sm.add_sample(sample.dict())
    
    samples = sm.get_samples()
    assert len(samples) == 1
    assert samples[0]['name'] == "Snare"
    assert samples[0]['sample_type'] == SampleType.ONE_SHOT
    assert samples[0]['asset_type'] == AssetType.SAMPLE
