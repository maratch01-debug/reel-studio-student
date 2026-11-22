import math

CKPT = 'ltx-2.3-22b-dev-fp8.safetensors'
LORA11 = 'ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors'
UPS = 'ltx-2.3-spatial-upscaler-x2-1.1.safetensors'
SIGMAS = '1.0, 0.99375, 0.9875, 0.975, 0.909375, 0.725, 0.421875, 0.0'
SIGMAS2 = '0.85, 0.7250, 0.4219, 0.0'

def workflow(prompt, tag, pre, seconds, seed, strength):
    w, h = 768, 1344
    frames = math.ceil((seconds + 0.15) * 3) * 8 + 1
    neg = 'blurry, distorted face, extra fingers, extra limbs, flicker, text, watermark'
    wf = {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': CKPT}},
        '2': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['1', 0], 'lora_name': LORA11, 'strength_model': 0.5}},
        '3': {'class_type': 'LTXAVTextEncoderLoader', 'inputs': {'text_encoder': 'gemma_3_12B_it_fp4_mixed.safetensors', 'ckpt_name': CKPT, 'device': 'default'}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['3', 0]}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'text': neg, 'clip': ['3', 0]}},
        '6': {'class_type': 'LTXVConditioning', 'inputs': {'positive': ['4', 0], 'negative': ['5', 0], 'frame_rate': 24.0}},
        '7': {'class_type': 'LTXVAudioVAELoader', 'inputs': {'ckpt_name': CKPT}},
        '8': {'class_type': 'LoadAudio', 'inputs': {'audio': f'ia2v_{tag}.wav'}},
        '9': {'class_type': 'TrimAudioDuration', 'inputs': {'audio': ['8', 0], 'start_index': 0.0, 'duration': frames / 24}},
        '10': {'class_type': 'LTXVAudioVAEEncode', 'inputs': {'audio': ['9', 0], 'audio_vae': ['7', 0]}},
        '11': {'class_type': 'SolidMask', 'inputs': {'value': 0.0, 'width': w, 'height': h}},
        '12': {'class_type': 'SetLatentNoiseMask', 'inputs': {'samples': ['10', 0], 'mask': ['11', 0]}},
        '13': {'class_type': 'LoadImage', 'inputs': {'image': f'ia2v_{tag}.png'}},
        '14': {'class_type': 'LTXVPreprocess', 'inputs': {'image': ['13', 0], 'img_compression': 18}},
        # стадия 1: половинное разрешение
        '15': {'class_type': 'EmptyLTXVLatentVideo', 'inputs': {'width': w // 2, 'height': h // 2, 'length': frames, 'batch_size': 1}},
        '16': {'class_type': 'LTXVImgToVideoInplace', 'inputs': {'vae': ['1', 2], 'image': ['14', 0], 'latent': ['15', 0], 'strength': strength, 'bypass': False}},
        '17': {'class_type': 'LTXVConcatAVLatent', 'inputs': {'video_latent': ['16', 0], 'audio_latent': ['12', 0]}},
        '18': {'class_type': 'CFGGuider', 'inputs': {'model': ['2', 0], 'positive': ['6', 0], 'negative': ['6', 1], 'cfg': 1.0}},
        '19': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        '20': {'class_type': 'ManualSigmas', 'inputs': {'sigmas': SIGMAS}},
        '21': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': seed}},
        '22': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['21', 0], 'guider': ['18', 0], 'sampler': ['19', 0], 'sigmas': ['20', 0], 'latent_image': ['17', 0]}},
        '23': {'class_type': 'LTXVSeparateAVLatent', 'inputs': {'av_latent': ['22', 0]}},
        # стадия 2: апскейл латента x2 и дорисовка деталей
        '30': {'class_type': 'LatentUpscaleModelLoader', 'inputs': {'model_name': UPS}},
        '31': {'class_type': 'LTXVLatentUpsampler', 'inputs': {'samples': ['23', 0], 'upscale_model': ['30', 0], 'vae': ['1', 2]}},
        '32': {'class_type': 'LTXVImgToVideoInplace', 'inputs': {'vae': ['1', 2], 'image': ['14', 0], 'latent': ['31', 0], 'strength': 1.0, 'bypass': False}},
        '33': {'class_type': 'LTXVConcatAVLatent', 'inputs': {'video_latent': ['32', 0], 'audio_latent': ['12', 0]}},
        '34': {'class_type': 'LTXVCropGuides', 'inputs': {'positive': ['6', 0], 'negative': ['6', 1], 'latent': ['23', 0]}},
        '35': {'class_type': 'CFGGuider', 'inputs': {'model': ['2', 0], 'positive': ['34', 0], 'negative': ['34', 1], 'cfg': 1.0}},
        '36': {'class_type': 'ManualSigmas', 'inputs': {'sigmas': SIGMAS2}},
        '37': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': 42}},
        '38': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['37', 0], 'guider': ['35', 0], 'sampler': ['19', 0], 'sigmas': ['36', 0], 'latent_image': ['33', 0]}},
        '39': {'class_type': 'LTXVSeparateAVLatent', 'inputs': {'av_latent': ['38', 0]}},
        '40': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['39', 0], 'vae': ['1', 2], 'tile_size': 768, 'overlap': 64, 'temporal_size': 4096, 'temporal_overlap': 4}},
        '41': {'class_type': 'SaveImage', 'inputs': {'images': ['40', 0], 'filename_prefix': pre}},
    }
    return wf
