from redis_doctor.collectors.keyspace import group_prefixes, tokenize_prefix
from redis_doctor.models.sample import KeyInfo


def test_tokenize_depth():
    assert tokenize_prefix("session:user:123", 1, ":.|/_") == "session"
    assert tokenize_prefix("session:user:123", 2, ":.|/_") == "session:user"
    assert tokenize_prefix("queue:email:pending", 2, ":.|/_") == "queue:email"


def test_tokenize_fewer_tokens_than_depth():
    assert tokenize_prefix("plainkey", 2, ":.|/_") == "plainkey"
    assert tokenize_prefix("lock:42", 2, ":.|/_") == "lock:42"


def test_tokenize_mixed_separators():
    assert tokenize_prefix("metrics.http.200", 2, ":.|/_") == "metrics.http"
    assert tokenize_prefix("a/b/c", 2, ":.|/_") == "a/b"


def test_group_prefixes_counts_and_memory():
    keys = [
        KeyInfo(key="session:user:1", type="string", memory_bytes=100),
        KeyInfo(key="session:user:2", type="string", memory_bytes=200),
        KeyInfo(key="cache:x:1", type="string", memory_bytes=50),
    ]
    by_count, by_memory = group_prefixes(keys, 2, ":.|/_")
    assert by_count[0].prefix == "session:user"
    assert by_count[0].count == 2
    assert by_memory[0].prefix == "session:user"
    assert by_memory[0].memory_bytes == 300
