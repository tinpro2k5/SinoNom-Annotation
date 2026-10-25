"""Tests for Step 4 draft saving and hydration."""
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app import create_app, parser, resolve_app_paths
from annotation.workflow import Workflow
from annotation.state import new_state, set_verified_content, initialize_alignment
from annotation.bbox import add_bbox
from annotation.status import update_status
from annotation.io import atomic_write, read_json


class Step4DraftTests(unittest.TestCase):
    def _create_engine_and_image(self, root):
        image = root / '1.png'
        Image.new('RGB', (100, 100)).save(image)
        source = root / 'source.json'
        atomic_write(source, [{'noi_dung': [{'ky_hieu': '1', 'chuyen_muc': [
            {'tieu_de': 'Nguyên văn chữ Hán Nôm', 'van_ban': '永寺'}]}]}])
        options = parser().parse_args([
            '--image-dir', str(root), '--source-json', str(source),
            '--output-dir', str(root / 'out'), '--skip-detection'])
        options = resolve_app_paths(options)
        engine = Workflow(options)
        return engine, image, source, options

    def _setup_step4_state(self, engine, image):
        state = engine.open_image(image)
        set_verified_content(state, state['draft_content'], '永寺')
        state['workflow']['content_verified'] = True
        for x in (10, 40):
            add_bbox(state, [x, 10, x + 20, 30])
        initialize_alignment(state)
        state['current_step'] = 4
        state['selected_box_id'] = '1'
        state['selected_region_uid'] = state['region_uid_by_box_id']['1']
        return state

    def test_save_and_hydrate_step4_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            engine, image, _, _ = self._create_engine_and_image(root)
            state = self._setup_step4_state(engine, image)

            # Modify status, flags, damage level, and sequence
            uid1 = state['region_uid_by_box_id']['1']
            uid2 = state['region_uid_by_box_id']['2']
            update_status(state, uid1, 'damaged', damage_level=2, suspicious=True)
            update_status(state, uid2, 'damaged', unknown=True)
            state['annotations'] = {'1': '寺', '2': '永'}
            state['text_sequence'] = ['寺', '永']
            state['text_token_ids'] = ['2', '1']

            draft_path = engine.save_draft(state)
            self.assertTrue(draft_path.exists())
            draft_doc = read_json(draft_path)
            self.assertEqual(draft_doc.get('draft_step'), 4)
            self.assertEqual(draft_doc.get('annotations'), {'1': '寺', '2': '永'})
            self.assertEqual(draft_doc.get('reading_order'), [1, 2])
            self.assertEqual(draft_doc.get('text_sequence'), ['寺', '永'])
            self.assertEqual(draft_doc.get('text_token_ids'), ['2', '1'])
            self.assertEqual(draft_doc['regions'][uid1]['status'], 'damaged')
            self.assertEqual(draft_doc['regions'][uid1]['damage_level'], 2)
            self.assertTrue(draft_doc['regions'][uid1]['suspicious'])
            self.assertTrue(draft_doc['regions'][uid2]['unknown'])

            # Hydrate via open_image
            hydrated = engine.open_image(image)
            self.assertEqual(hydrated['current_step'], 4)
            self.assertTrue(hydrated['workflow']['alignment_valid'])
            self.assertTrue(hydrated['workflow']['bbox_valid'])
            self.assertEqual(hydrated['annotations'], {'1': '寺', '2': '永'})
            self.assertEqual(hydrated['reading_order'], [1, 2])
            self.assertEqual(hydrated['text_sequence'], ['寺', '永'])
            self.assertEqual(hydrated['text_token_ids'], ['2', '1'])
            self.assertEqual(hydrated['selected_box_id'], '1')
            self.assertEqual(hydrated['selected_region_uid'], uid1)
            self.assertEqual(hydrated['regions'][uid1]['damage_level'], 2)
            self.assertTrue(hydrated['regions'][uid1]['suspicious'])
            self.assertTrue(hydrated['regions'][uid2]['unknown'])
            self.assertEqual(hydrated['bounding_boxes']['1']['damage_level'], 2)
            self.assertTrue(hydrated['bounding_boxes']['1']['suspicious'])

            # Verify load_source_info and load_notification_markup
            self.assertIsNotNone(hydrated.get('load_source_info'))
            self.assertEqual(hydrated['load_source_info']['source'], 'draft')
            self.assertEqual(hydrated['load_source_info']['file_name'], '1_step3.json')
            self.assertEqual(hydrated['load_source_info']['step'], 4)
            from ui.presentation import load_notification_markup
            markup = load_notification_markup(hydrated)
            self.assertIn('load-source-toast', markup)
            self.assertIn('Bản nháp (Draft)', markup)
            self.assertIn('1_step3.json', markup)
            self.assertIn(hydrated['load_source_info']['mtime_str'], markup)
            self.assertIn('Step 4', markup)

    def test_load_source_info_for_saved_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            engine, image, _, _ = self._create_engine_and_image(root)
            state = self._setup_step4_state(engine, image)
            from crop.crop import image_resize, crop_document
            resize = image_resize([100, 100], [100, 100])
            crop = crop_document(image.name, [0, 0, 100, 100], [100, 100])['crop']
            final_doc = {
                'image': image.name,
                'bounding_boxes': state['bounding_boxes'],
                'annotations': state['annotations'],
                'crop': crop,
                'image_resize': resize,
            }
            atomic_write(engine.output / '1.json', final_doc)

            loaded = engine.open_image(image)
            self.assertIsNotNone(loaded.get('load_source_info'))
            self.assertEqual(loaded['load_source_info']['source'], 'json')
            self.assertEqual(loaded['load_source_info']['file_name'], '1.json')
            self.assertEqual(loaded['load_source_info']['step'], 4)
            self.assertTrue(loaded['load_source_info']['mtime_str'])

            # When loaded reaches step 4
            loaded['current_step'] = 4
            from ui.presentation import load_notification_markup
            markup = load_notification_markup(loaded)
            self.assertIn('load-source-toast', markup)
            self.assertIn('File JSON đã lưu', markup)
            self.assertIn('1.json', markup)
            self.assertIn(loaded['load_source_info']['mtime_str'], markup)

    def test_legacy_step3_draft_backward_compatibility(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            engine, image, _, _ = self._create_engine_and_image(root)
            state = self._setup_step4_state(engine, image)
            state['current_step'] = 3

            # Save draft without annotations / with draft_step 3
            draft_path = engine.save_draft(state)
            draft_doc = read_json(draft_path)
            # Remove draft_step to simulate older draft
            del draft_doc['draft_step']
            atomic_write(draft_path, draft_doc)

            hydrated = engine.open_image(image)
            self.assertEqual(hydrated['current_step'], 3)
            self.assertEqual(len(hydrated['regions']), 2)

    def test_save_progress_draft_app_callback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            engine, image, source, options = self._create_engine_and_image(root)
            app = create_app(options)
            save_progress = next(f.fn for f in app.fns.values()
                                 if f.fn and f.fn.__name__ == 'save_progress_draft')

            state = self._setup_step4_state(engine, image)
            state.update(image_path=str(image), image_url='image.jpg')
            ctx = dict(active=state, drafts={})

            # Live selection bridge payload from Step 4 with unassigned damage level (still drafts successfully)
            payload = {
                'statuses': {'1': 'damaged', '2': 'intact'},
                'damage_levels': {'1': None, '2': None},
                'unknowns': {'1': False, '2': False},
                'unavailable_fonts': {'1': False, '2': False},
                'expert_predictions': {'1': False, '2': False},
                'suspiciouses': {'1': True, '2': False},
                'textSequence': ['寺', '永'],
                'tokenOrder': ['2', '1'],
            }
            result = save_progress(ctx, json.dumps(payload))
            self.assertEqual(result[0]['active']['current_step'], 4)
            self.assertEqual(result[0]['active']['annotations'], {'1': '寺', '2': '永'})
            self.assertTrue(result[0]['active']['bounding_boxes']['1']['suspicious'])

            # Verify on-disk file
            draft_path = engine.draft_path(image.name)
            self.assertTrue(draft_path.exists())
            saved_doc = read_json(draft_path)
            self.assertEqual(saved_doc['draft_step'], 4)
            self.assertEqual(saved_doc['annotations'], {'1': '寺', '2': '永'})
            self.assertTrue(str(image) in result[0]['drafts'])
