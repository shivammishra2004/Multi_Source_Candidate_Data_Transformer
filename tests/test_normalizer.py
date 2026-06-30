from src.normalizer import Normalizer

def test_format_phone_strips_uk_punctuation():
    # 1. ARRANGE
    raw_phone = "+44 (0) 7911-123456"
    expected_output = "+4407911123456" # based on digits extraction rule
    
    # 2. ACT
    actual_output = Normalizer.format_phone(raw_phone)
    
    # 3. ASSERT
    assert actual_output == expected_output

def test_format_phone_returns_null_on_garbage():
    # 1. ARRANGE
    raw_phone = "ext 404"
    expected_output = None
    
    # 2. ACT
    actual_output = Normalizer.format_phone(raw_phone)
    
    # 3. ASSERT
    assert actual_output is expected_output
