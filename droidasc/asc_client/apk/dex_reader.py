import struct


_U32_FROM = struct.Struct("<I").unpack_from


def _skip_uleb128(buf, off : int) -> int:
    while buf[off] & 0x80:
        off += 1
    return off + 1


def _read_string_data_bytes(buf, str_off : int) -> bytes:
    # The leading uleb128 stores UTF-16 code-unit count, not byte length.
    # Reading to the terminating NUL is therefore required for MUTF-8.
    ptr = _skip_uleb128(buf, str_off)
    end = buf.find(b"\x00", ptr)
    if end < 0:
        raise ValueError("unterminated string_data_item")
    return buf[ptr:end]


def _find_type_idx(buf, target_bytes : bytes) -> int:
    if len(buf) < 0x70 or buf[:3] != b"dex":
        return -1

    string_ids_size = _U32_FROM(buf, 0x38)[0]
    string_ids_off = _U32_FROM(buf, 0x3C)[0]
    type_ids_size = _U32_FROM(buf, 0x40)[0]
    type_ids_off = _U32_FROM(buf, 0x44)[0]

    if string_ids_size == 0 or type_ids_size == 0:
        return -1
    if string_ids_off + string_ids_size * 4 > len(buf):
        raise ValueError("bad string_ids range")
    if type_ids_off + type_ids_size * 4 > len(buf):
        raise ValueError("bad type_ids range")

    left = 0
    right = type_ids_size - 1
    # type_ids follows string-id order. DEX MUTF-8 bytes preserve UTF-16
    # code-unit ordering, so compare encoded descriptors without decoding.
    while left <= right:
        mid = (left + right) >> 1
        str_idx = _U32_FROM(buf, type_ids_off + (mid << 2))[0]
        if str_idx >= string_ids_size:
            raise ValueError("bad type_id->string_idx")
        str_off = _U32_FROM(buf, string_ids_off + (str_idx << 2))[0]
        if str_off >= len(buf):
            raise ValueError("bad string_data_off")

        cls_bytes = _read_string_data_bytes(buf, str_off)
        if cls_bytes == target_bytes:
            return mid
        if cls_bytes < target_bytes:
            left = mid + 1
        else:
            right = mid - 1

    return -1


def _class_defs_contains_type_idx(buf, type_idx : int) -> bool:
    class_defs_size = _U32_FROM(buf, 0x60)[0]
    class_defs_off = _U32_FROM(buf, 0x64)[0]

    if class_defs_size == 0:
        return False

    class_defs_end = class_defs_off + (class_defs_size << 5)
    if class_defs_end > len(buf):
        raise ValueError("bad class_defs range")

    needle = type_idx.to_bytes(4, "little")
    pos = buf.find(needle, class_defs_off, class_defs_end)
    while pos != -1:
        # The same four bytes may occur in another class_def field. class_idx
        # is valid only at the first word of each 32-byte class_def_item.
        if ((pos - class_defs_off) & 0x1F) == 0:
            return True
        pos = buf.find(needle, pos + 1, class_defs_end)
    return False


def _dex_defines_class(buf, target_bytes : bytes) -> bool:
    type_idx = _find_type_idx(buf, target_bytes)
    if type_idx < 0:
        return False
    return _class_defs_contains_type_idx(buf, type_idx)


def _decode_name(raw_name : bytes) -> str:
    try:
        return raw_name.decode("utf-8")
    except UnicodeDecodeError:
        # Surrogate-pair MUTF-8 is invalid strict UTF-8. Import the fallback
        # only for such names so ordinary listclass startup stays cheap.
        from droidasc.asc_core.utils.tinydex import _decode_mutf8_fallback

        return _decode_mutf8_fallback(raw_name)


def list_dex_classes(buf, prefix : str = None, prefix_bytes : bytes = None):
    if len(buf) < 0x70 or buf[:3] != b"dex":
        raise ValueError("invalid DEX header")

    string_ids_size = _U32_FROM(buf, 0x38)[0]
    string_ids_off = _U32_FROM(buf, 0x3C)[0]
    type_ids_size = _U32_FROM(buf, 0x40)[0]
    type_ids_off = _U32_FROM(buf, 0x44)[0]
    class_defs_size = _U32_FROM(buf, 0x60)[0]
    class_defs_off = _U32_FROM(buf, 0x64)[0]

    if class_defs_size == 0:
        return []
    if string_ids_off + string_ids_size * 4 > len(buf):
        raise ValueError("bad string_ids range")
    if type_ids_off + type_ids_size * 4 > len(buf):
        raise ValueError("bad type_ids range")
    if class_defs_off + class_defs_size * 32 > len(buf):
        raise ValueError("bad class_defs range")

    names = []
    append = names.append
    class_defs_end = class_defs_off + class_defs_size * 32
    for class_def_off in range(class_defs_off, class_defs_end, 32):
        type_idx = _U32_FROM(buf, class_def_off)[0]
        if type_idx >= type_ids_size:
            raise ValueError("bad class_def->type_idx")
        string_idx = _U32_FROM(buf, type_ids_off + (type_idx << 2))[0]
        if string_idx >= string_ids_size:
            raise ValueError("bad type_id->string_idx")
        string_off = _U32_FROM(buf, string_ids_off + (string_idx << 2))[0]
        if string_off >= len(buf):
            raise ValueError("bad string_data_off")
        try:
            raw_name = _read_string_data_bytes(buf, string_off)
        except IndexError as error:
            raise ValueError("bad string_data_off") from error

        # ASCII prefixes can be rejected before decoding every class name.
        if prefix_bytes is not None:
            if raw_name.startswith(prefix_bytes):
                append(_decode_name(raw_name))
        else:
            name = _decode_name(raw_name)
            if prefix is None or name.startswith(prefix):
                append(name)
    return names
