#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <cstring>

#include <dev/devs.hpp>
#include <dev/dev.hpp>

namespace py = pybind11;

struct ObsbotError : public std::runtime_error {
	using std::runtime_error::runtime_error;
};

static void check_ok(int32_t ret, const char *what)
{
	if (ret != RM_RET_OK) {
		throw ObsbotError(std::string(what) + " failed with code " +
				   std::to_string(ret));
	}
}

/// DevDataArray's int32 view is a fixed 16-entry array (see
/// libdev's dev.hpp), and `len` comes straight off the device, so it is
/// never trusted as an index bound without clamping first.
static constexpr int32_t kMaxPresetSlots = 16;
static constexpr int32_t kMaxPresetSlotsTiny1 = 3;

static inline bool is_tiny1_family(ObsbotProductType type)
{
	return type == ObsbotProdTiny || type == ObsbotProdTiny4k;
}

static int32_t clamp_preset_list_len(int32_t len)
{
	if (len < 0) {
		return 0;
	}
	if (len > kMaxPresetSlots) {
		return kMaxPresetSlots;
	}
	return len;
}

static py::dict status_to_dict(const Device::CameraStatus &status)
{
	py::dict d;
	d["zoom_ratio"] = status.tiny.zoom_ratio;
	d["ai_target"] = status.tiny.ai_target;
	d["ai_mode"] = (status.tiny.ai_mode != 0 || status.tiny.ai_target != 0) ? 1 : 0;
	d["dev_status"] = status.tiny.dev_status;
	d["vertical"] = status.tiny.vertical;
	d["hdr"] = status.tiny.hdr;
	return d;
}

PYBIND11_MODULE(obsbot_bridge, m)
{
	m.doc() = "Thin pybind11 bridge over the OBSBOT libdev SDK";

	py::register_exception<ObsbotError>(m, "ObsbotError");

	py::enum_<ObsbotProductType>(m, "ProductType")
		.value("Tiny", ObsbotProdTiny)
		.value("Tiny4k", ObsbotProdTiny4k)
		.value("Tiny2", ObsbotProdTiny2)
		.value("Tiny2Lite", ObsbotProdTiny2Lite)
		.value("TinySE", ObsbotProdTinySE)
		.export_values();

	py::enum_<Device::AiVerticalTrackType>(m, "TrackMode")
		.value("Standard", Device::AiVTrackStandard)
		.value("Headroom", Device::AiVTrackHeadroom)
		.value("Motion", Device::AiVTrackMotion)
		.export_values();

	py::class_<Device, std::shared_ptr<Device>>(m, "Device")
		.def_property_readonly("sn", &Device::devSn)
		.def_property_readonly("name", [](Device &d) { return d.devName(); })
		.def_property_readonly("product_type", &Device::productType)
		.def("set_status_callback", [](Device &d, py::function callback) {
			auto shared_cb = std::make_shared<py::function>(std::move(callback));
			d.setDevStatusCallbackFunc(
				[shared_cb](void *, const void *data) {
					const auto *status =
						static_cast<const Device::CameraStatus *>(data);
					py::gil_scoped_acquire acquire;
					try {
						(*shared_cb)(status_to_dict(*status));
					} catch (const std::exception &e) {
						std::cerr << "status callback error: "
							  << e.what() << std::endl;
					}
				},
				nullptr);
			d.enableDevStatusCallback(true);
		})
		.def("set_gimbal_speed", [](Device &d, double pitch, double pan) {
			check_ok(d.aiSetGimbalSpeedCtrlR(pitch, pan),
				 "set_gimbal_speed");
		})
		.def("stop_gimbal", [](Device &d) {
			// Speed 0 stops the motors immediately across all hardware models
			d.aiSetGimbalSpeedCtrlR(0.0, 0.0);
			if (!is_tiny1_family(d.productType())) {
				check_ok(d.aiSetGimbalStop(), "stop_gimbal");
			}
		})
		.def("set_ai_enabled", [](Device &d, bool enabled) {
			if (is_tiny1_family(d.productType())) {
				d.aiSetEnabledR(enabled);
				d.aiSetTargetSelectR(enabled);
			} else {
				check_ok(d.aiSetEnabledR(enabled), "set_ai_enabled");
			}
		})
		.def("set_tracking_mode", [](Device &d,
					      Device::AiVerticalTrackType mode) {
			check_ok(d.aiSetTrackingModeR(mode), "set_tracking_mode");
		})
		.def("get_gimbal_angle", [](Device &d) {
			py::dict out;
			if (is_tiny1_family(d.productType())) {
				float xyz[3] = {0.f};
				check_ok(d.gimbalGetAttitudeInfoR(xyz),
					 "get_gimbal_angle");
				out["roll"] = xyz[0];
				out["pitch"] = xyz[1];
				out["yaw"] = xyz[2];
			} else {
				Device::AiGimbalStateInfo info{};
				check_ok(d.aiGetGimbalStateR(&info), "get_gimbal_angle");
				out["pitch"] = info.pitch_euler;
				out["yaw"] = info.yaw_euler;
				out["roll"] = info.roll_euler;
			}
			return out;
		})
		.def("set_zoom", [](Device &d, float zoom) {
			// Normalized 1.0~2.0 absolute zoom. This is the path
			// that reliably drives the Tiny2 firmware.
			int32_t result;
			{
				py::gil_scoped_release release;
				result = d.cameraSetZoomAbsoluteR(zoom);
			}
			check_ok(result, "set_zoom");
		})
		.def("set_zoom_with_speed", [](Device &d, float zoom, uint32_t speed) {
			const uint32_t zoom_ratio = static_cast<uint32_t>(zoom * 100.0f + 0.5f);
			int32_t result;
			{
				py::gil_scoped_release release;
				result = d.cameraSetZoomWithSpeedAbsoluteR(zoom_ratio, speed);
			}
			check_ok(result, "set_zoom_with_speed");
		})
		.def("get_zoom", [](Device &d) {
			float zoom = 0.f;
			check_ok(d.cameraGetZoomAbsoluteR(zoom), "get_zoom");
			return zoom;
		})
		.def("get_zoom_range", [](Device &d) {
			Device::UvcParamRange range{};
			check_ok(d.cameraGetRangeZoomAbsoluteR(range), "get_zoom_range");
			py::dict out;
			out["min"] = range.min_;
			out["max"] = range.max_;
			out["step"] = range.step_;
			return out;
		})
		.def("set_brightness", [](Device &d, int32_t v) {
			check_ok(d.cameraSetImageBrightnessR(v), "set_brightness");
		})
		.def("get_brightness", [](Device &d) {
			int32_t v = 0;
			check_ok(d.cameraGetImageBrightnessR(v), "get_brightness");
			return v;
		})
		.def("get_brightness_range", [](Device &d) {
			Device::UvcParamRange range{};
			check_ok(d.cameraGetRangeImageBrightnessR(range),
				 "get_brightness_range");
			py::dict out;
			out["min"] = range.min_;
			out["max"] = range.max_;
			out["step"] = range.step_;
			out["default"] = range.default_;
			return out;
		})
		.def("set_contrast", [](Device &d, int32_t v) {
			check_ok(d.cameraSetImageContrastR(v), "set_contrast");
		})
		.def("get_contrast", [](Device &d) {
			int32_t v = 0;
			check_ok(d.cameraGetImageContrastR(v), "get_contrast");
			return v;
		})
		.def("get_contrast_range", [](Device &d) {
			Device::UvcParamRange range{};
			check_ok(d.cameraGetRangeImageContrastR(range),
				 "get_contrast_range");
			py::dict out;
			out["min"] = range.min_;
			out["max"] = range.max_;
			out["step"] = range.step_;
			out["default"] = range.default_;
			return out;
		})
		.def("set_saturation", [](Device &d, int32_t v) {
			check_ok(d.cameraSetImageSaturationR(v), "set_saturation");
		})
		.def("get_saturation", [](Device &d) {
			int32_t v = 0;
			check_ok(d.cameraGetImageSaturationR(v), "get_saturation");
			return v;
		})
		.def("get_saturation_range", [](Device &d) {
			Device::UvcParamRange range{};
			check_ok(d.cameraGetRangeImageSaturationR(range),
				 "get_saturation_range");
			py::dict out;
			out["min"] = range.min_;
			out["max"] = range.max_;
			out["step"] = range.step_;
			out["default"] = range.default_;
			return out;
		})
		.def("set_sharpness", [](Device &d, int32_t v) {
			check_ok(d.cameraSetImageSharpR(v), "set_sharpness");
		})
		.def("get_sharpness", [](Device &d) {
			int32_t v = 0;
			check_ok(d.cameraGetImageSharpR(v), "get_sharpness");
			return v;
		})
		.def("get_sharpness_range", [](Device &d) {
			Device::UvcParamRange range{};
			check_ok(d.cameraGetRangeImageSharpR(range),
				 "get_sharpness_range");
			py::dict out;
			out["min"] = range.min_;
			out["max"] = range.max_;
			out["step"] = range.step_;
			out["default"] = range.default_;
			return out;
		})
		.def("list_presets", [](Device &d) {
			py::list out;
			if (is_tiny1_family(d.productType())) {
				for (int32_t i = 0; i < kMaxPresetSlotsTiny1; ++i) {
					Device::PresetPosInfo info{};
					if (d.aiGetGimbalPresetInfoWithIdR(&info, i) == RM_RET_OK &&
					    info.name_len > 0) {
						py::dict item;
						item["id"] = i;
						item["name"] = std::string(info.name,
									    static_cast<size_t>(info.name_len));
						item["pitch"] = info.pitch;
						item["yaw"] = info.yaw;
						item["roll"] = info.roll;
						item["zoom"] = info.zoom;
						out.append(item);
					}
				}
				return out;
			}
			Device::DevDataArray ids{};
			check_ok(d.aiGetGimbalPresetListR(&ids), "list_presets");
			const int32_t len = clamp_preset_list_len(ids.len);
			for (int32_t i = 0; i < len; ++i) {
				int32_t id = ids.data_int32[i];
				Device::PresetPosInfo info{};
				check_ok(d.aiGetGimbalPresetInfoWithIdR(&info, id),
					 "get_preset_info");
				py::dict item;
				item["id"] = id;
				item["name"] = std::string(info.name,
							    static_cast<size_t>(info.name_len));
				item["pitch"] = info.pitch;
				item["yaw"] = info.yaw;
				item["roll"] = info.roll;
				item["zoom"] = info.zoom;
				out.append(item);
			}
			return out;
		})
		.def("add_preset", [](Device &d, const std::string &name,
				       float pitch, float yaw, float roll,
				       float zoom, int32_t target_id = -1) {
			int32_t new_id = target_id;
			if (new_id < 0) {
				if (is_tiny1_family(d.productType())) {
					bool used[kMaxPresetSlotsTiny1] = {false};
					for (int32_t i = 0; i < kMaxPresetSlotsTiny1; ++i) {
						Device::PresetPosInfo info{};
						if (d.aiGetGimbalPresetInfoWithIdR(&info, i) == RM_RET_OK &&
						    info.name_len > 0) {
							used[i] = true;
						}
					}
					for (int32_t i = 0; i < kMaxPresetSlotsTiny1; ++i) {
						if (!used[i]) {
							new_id = i;
							break;
						}
					}
					if (new_id < 0) {
						throw ObsbotError(
							"add_preset failed: no free preset slot (max 3)");
					}
				} else {
					Device::DevDataArray ids{};
					check_ok(d.aiGetGimbalPresetListR(&ids), "add_preset");
					const int32_t len = clamp_preset_list_len(ids.len);
					bool used[kMaxPresetSlots] = {false};
					for (int32_t i = 0; i < len; ++i) {
						const int32_t existing = ids.data_int32[i];
						if (existing >= 0 && existing < kMaxPresetSlots) {
							used[existing] = true;
						}
					}
					for (int32_t i = 0; i < kMaxPresetSlots; ++i) {
						if (!used[i]) {
							new_id = i;
							break;
						}
					}
					if (new_id < 0) {
						throw ObsbotError(
							"add_preset failed: no free preset slot (max 16)");
					}
				}
			}

			Device::PresetPosInfo info{};
			info.id = new_id;
			info.pitch = pitch;
			info.yaw = yaw;
			info.roll = roll;
			info.zoom = zoom;
			std::string truncated = name.substr(0, 63);
			memcpy(info.name, truncated.c_str(), truncated.size());
			info.name_len = static_cast<int32_t>(truncated.size());
			check_ok(d.aiAddGimbalPresetR(&info), "add_preset");
			return info.id;
		}, py::arg("name"), py::arg("pitch"), py::arg("yaw"),
		   py::arg("roll"), py::arg("zoom"), py::arg("id") = -1)
		.def("delete_preset", [](Device &d, int32_t id) {
			check_ok(d.aiDelGimbalPresetR(id), "delete_preset");
		})
		.def("goto_preset", [](Device &d, int32_t id) {
			if (is_tiny1_family(d.productType())) {
				// Disengage AI target tracking so gimbal moves freely to preset
				d.aiSetTargetSelectR(false);
				d.aiSetEnabledR(false);
			}
			check_ok(d.aiTrgGimbalPresetR(id), "goto_preset");
		})
		.def("rename_preset", [](Device &d, int32_t id,
					  const std::string &name) {
			check_ok(d.aiSetGimbalPresetNameWithIdR(name, id),
				 "rename_preset");
		});

	m.def("get_device_by_sn", [](const std::string &sn) {
		return Devices::get().getDevBySn(sn);
	});

	m.def("set_device_changed_callback", [](py::function callback) {
		// Intentionally leaked: a py::function held in a function-local
		// static would be destroyed during C++ static teardown, i.e.
		// after Py_Finalize, and its Py_DECREF would run against an
		// already-torn-down interpreter (classic pybind11 crash at exit).
		static py::function *stored_callback = nullptr;
		if (stored_callback == nullptr) {
			stored_callback = new py::function(std::move(callback));
		} else {
			*stored_callback = std::move(callback);
		}
		Devices::get().setDevChangedCallback(
			[](std::string sn, bool connected, void *) {
				py::gil_scoped_acquire acquire;
				try {
					(*stored_callback)(sn, connected);
				} catch (const std::exception &e) {
					std::cerr << "device changed callback error: "
						  << e.what() << std::endl;
				}
			},
			nullptr);
	});

	// GIL released for the duration: Devices::close() joins the SDK's
	// detection thread, and this bridge's own callbacks acquire the GIL
	// from that thread — holding it here would deadlock the join.
	m.def("close", []() { Devices::get().close(); },
	      py::call_guard<py::gil_scoped_release>());

	m.def("list_devices", []() {
		py::list out;
		for (auto &dev : Devices::get().getDevList()) {
			py::dict item;
			item["sn"] = dev->devSn();
			item["name"] = dev->devName();
			item["product_type"] = dev->productType();
			out.append(item);
		}
		return out;
	});
}
