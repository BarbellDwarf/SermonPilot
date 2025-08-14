from audio_processing import process_sermon_audio


def test_no_compression():
    input_path = 'tests/2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3'
    output_path = 'tests/test_no_compression_output.mp3'
    result = process_sermon_audio(
        input_path,
        output_path,
        noise_reduction=True,
        amplify=False,
        normalize=True,
        gain_db=0.0,
        target_level_db=-21.0
    )
    print(f"Test no compression result: {result}")
    print(f"Output file: {output_path}")

if __name__ == '__main__':
    test_no_compression()
