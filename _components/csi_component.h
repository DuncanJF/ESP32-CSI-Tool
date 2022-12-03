#ifndef ESP32_CSI_CSI_COMPONENT_H
#define ESP32_CSI_CSI_COMPONENT_H

#include "time_component.h"
#include "math.h"
#include <sstream>
#include <iostream>
#include <iomanip>
#include <bitset>
#include <string>
#include <cstring>
#include <chrono>
#include "esp_system.h"

#include "common_component.h"

enum DataExportFormat
{
	NOP = EXPORT_NOP,
	ORIG = EXPORT_CSV,
	FULL_AS_JSON = EXPORT_JSON,
	FULL_AS_BASE64 = EXPORT_BASE64
};
static const uint16_t data_export_format = DATA_EXPORT_FORMAT;
enum CsiExportFormat
{
	I8QI = 1
};
static const uint16_t csi_export_format = I8QI;

/* Compile time constants */
static const uint32_t BOM = 65534;

/* Runtime fixed values */
static uint8_t project_type;
static uint8_t this_mac[6] = {0};

/* Fixed length arrays.*/

#if DATA_EXPORT_FORMAT == EXPORT_JSON || DATA_EXPORT_FORMAT == EXPORT_CSV
char this_mac_str[20] = {0};
#endif

/* Metrics */
SemaphoreHandle_t mutex = xSemaphoreCreateMutex();

#if DATA_EXPORT_FORMAT == EXPORT_BASE64
/* CRECORD AND HRECORD lengths are for the whole record excluding trailing '\n' and '\0' */
#ifdef CONFIG_ENABLE_STBC_HTLTF
/* CRECORD_LENGTH: Length of record then padded out to 4 byte alignment. */
#define CRECORD_LENGTH 680
/* HRECORD_LENGTH: Minimun 4*ceil(CRECORD_LENGTH/3), makes it 4 byte aligned by default. */
#define HRECORD_LENGTH 908
/* CTAIL = CRECORD_LENGTH%3 */
#define CTAIL 2
/* CALIGN = PADDING TO align crecord on 4 byte boundary */
#define CALIGN 1
#else
#define CRECORD_LENGTH 452
#define HRECORD_LENGTH 604
#define CTAIL 2
#define CALIGN 2
#endif
#define ENCLAST CRECORD_LENGTH - CTAIL
#elif DATA_EXPORT_FORMAT == EXPORT_JSON
/* CRECORD AND HRECORD lengths are for just the CSI data  part of the record. */
#ifdef CONFIG_ENABLE_STBC_HTLTF
#define CRECORD_LENGTH 612
#define HRECORD_LENGTH 816
#define CTAIL 0
#define CALIGN 0
#else
#define CRECORD_LENGTH 384
#define HRECORD_LENGTH 512
#define CTAIL 0
#define CALIGN 0
#endif
#define ENCLAST CRECORD_LENGTH - CTAIL
#endif

#if DATA_EXPORT_FORMAT == EXPORT_JSON || DATA_EXPORT_FORMAT == EXPORT_BASE64

static const char *Base64alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
// Add byte space for \0 but retain 4 byte alignment.
static unsigned char crecord[CRECORD_LENGTH + 4] = {0};
static const size_t sz_crecord = CRECORD_LENGTH;
static uint32_t rx_timestamp = 0;
static struct timeval tv_now;
static uint32_t tv_sec;
static uint32_t tv_usec;
// Add bytes for trailing \n and \0 but retain 4 byte alignment.
static char hrecord[HRECORD_LENGTH + 4] = {0};

inline void base64encode()
{
	size_t hpos = 0;
	memset(hrecord, '=', HRECORD_LENGTH);

	for (size_t i = 0; i < ENCLAST; i += 3)
	{
		int n = int(crecord[i]) << 16 | int(crecord[i + 1]) << 8 | crecord[i + 2];
		hrecord[hpos++] = Base64alphabet[n >> 18];
		hrecord[hpos++] = Base64alphabet[n >> 12 & 0x3F];
		hrecord[hpos++] = Base64alphabet[n >> 6 & 0x3F];
		hrecord[hpos++] = Base64alphabet[n & 0x3F];
	}
	if (CTAIL == 2)
	{
		int n = int(crecord[ENCLAST]) << 8 | int(crecord[ENCLAST + 1]);
		hrecord[hpos++] = Base64alphabet[n >> 10 & 0x3F];
		hrecord[hpos++] = Base64alphabet[n >> 4 & 0x03F];
		hrecord[hpos++] = Base64alphabet[n << 2 & 0x3F];
		hpos++;
	}
	else if (CTAIL)
	{
		int n = int(crecord[ENCLAST]);
		hrecord[hpos++] = Base64alphabet[n >> 2];
		hrecord[hpos++] = Base64alphabet[n << 4 & 0x3F];
		hpos += 2;
	}
	hrecord[hpos] = '\n';
}
#endif

#if DATA_EXPORT_FORMAT == EXPORT_BASE64
/* Fixed space for temporary values */
static int8_t sigval8 = 0;
static uint8_t unsigval8 = 0;
static uint16_t unsigval16 = 0;
static uint16_t csi_data_len = 0;

inline void data_export(void *ctx, wifi_csi_info_t *data)
{
	/*
	 * Copy the data bytewise then base64 the binary record for export.
	 *
	 * The resulting record for tranmission is less than half the size of the JSON and CSV encoded records.
	 *
	 * Simple delta t performance monitoring shows the code prior to this point executes in about 5-15us for the bytewise copy
	 * and 30-45us for the base64 encoding on an ESP32S3 running at 240MHz.
	 * The printf times shows variation but are connsistent with the set baud rate > 2500us @2000000 and > 1400us @4000000
	 * (remember the 8/10 encoding!)
	 * ie. the number of characters transmitted is a major limiting factor on the rate which data can be collected.
	 *
	 * Each record starts with a header which is constant for any given run.
	 * This is followed by the variable body.
	 * Since the system time will be synched externally the system time rather than monotonic time is used as a timestamp.
	 * The received packet timestamp is added as a prefix and suffix to the record body.  This makes a unique, per record, guard value.
	 * which helps identify data corruption due to transmission loss.
	 * There is an open question about what happens if new CSI data arrives while the current record is being processed.
	 * This should all be processed on CPU0 with the same priority and under the mutex.  
	 * The mutex should stop two data exports running on top of each other but that doesn't prevent the wifi_csi_info_t
	 * being written over by the behind the scenes WiFi receive chain.  The receive timestamp from wifi_csi_info_t
	 * written near the start and at the end of the export record act as guard values.  Ff wifi_csi_info_t does change while
	 * the export (c)record is being created then the guard value will not match.  So far the only guard value mismatches which
	 * have been seen were caused by data loss ov er UART.
	 *
	 * Fields from the wifi_csi_info_t and associated wifi_pkt_rx_ctrl_t can be combined as bitfields to reduce the transmission length
	 * further but the reduction is minor compared to swapping to binary encoding.
	 *
	 * See https://github.com/espressif/esp-idf/blob/6bb28c4cdc9c2434dc24662906fd8be857361c30/components/esp_wifi/include/esp_wifi_types.h#L371
	 * for field definitions with bit sizes.
	 *
	 * The captured and transmitted record lengths are fixed to accomodate the maximum number of CSI bytes to reduce memory (re)allocation.
	 */
	gettimeofday(&tv_now, NULL);
	memset(crecord, 0, CRECORD_LENGTH);
	unsigned char *p = crecord;
	wifi_csi_info_t csi_info = data[0];
	wifi_pkt_rx_ctrl_t rx_ctrl = csi_info.rx_ctrl;
	rx_timestamp = rx_ctrl.timestamp;
	// Output header (constant per device)
	memcpy(p, &BOM, sizeof(BOM)); // 4
	p += sizeof(BOM);
	memcpy(p, &data_export_format, sizeof(data_export_format)); // 2
	p += sizeof(data_export_format);
	memcpy(p, &sz_crecord, sizeof(sz_crecord)); // 4
	p += sizeof(sz_crecord);
	memcpy(p, &csi_export_format, sizeof(csi_export_format)); // 2
	p += sizeof(csi_export_format);
	memcpy(p, &project_type, sizeof(project_type)); // 1
	p += sizeof(project_type);
	memcpy(p, this_mac, sizeof(this_mac)); // 6
	p += sizeof(this_mac);
	// Output body
	tv_sec = tv_now.tv_sec;
	tv_usec = tv_now.tv_usec;
	memcpy(p, &tv_sec, sizeof(tv_sec)); // 4
	p += sizeof(tv_sec);
	memcpy(p, &tv_usec, sizeof(tv_usec)); // 4
	p += sizeof(tv_usec);
	memcpy(p, &rx_timestamp, sizeof(rx_timestamp)); // 4
	p += sizeof(rx_timestamp);
	memcpy(p, &csi_info.mac, sizeof(csi_info.mac)); // 6
	p += sizeof(csi_info.mac);
	sigval8 = rx_ctrl.rssi;
	memcpy(p, &sigval8, sizeof(sigval8)); // 1 ==38
	p += sizeof(sigval8);
	unsigval8 = rx_ctrl.rate;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.sig_mode;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.mcs;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.cwb;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.smoothing;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.not_sounding;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.aggregation;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.stbc;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1 ==40
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.fec_coding;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.sgi;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	sigval8 = rx_ctrl.noise_floor;
	memcpy(p, &sigval8, sizeof(sigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.ampdu_cnt;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.channel;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = rx_ctrl.secondary_channel;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	rx_timestamp = rx_ctrl.timestamp;
	memcpy(p, &rx_timestamp, sizeof(rx_timestamp)); // 4 ==50
	p += sizeof(rx_timestamp);
	unsigval8 = rx_ctrl.ant;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval16 = rx_ctrl.sig_len;
	memcpy(p, &unsigval16, sizeof(unsigval16)); // 2
	p += sizeof(unsigval16);
	unsigval8 = rx_ctrl.rx_state;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	unsigval8 = data->first_word_invalid;
	memcpy(p, &unsigval8, sizeof(unsigval8)); // 1
	p += sizeof(unsigval8);
	csi_data_len = data->len;
	memcpy(p, &csi_data_len, sizeof(csi_data_len)); // 2
	p += sizeof(csi_data_len);

	memcpy(p, data->buf, csi_data_len);
	p += MAX_CSI_BYTES;
	// Output tail
	rx_timestamp = rx_ctrl.timestamp;
	memcpy(p, &rx_timestamp, sizeof(rx_timestamp)); // 4
	p += sizeof(rx_timestamp);

	base64encode();
	printf("%s", hrecord);
	fflush(stdout);
}
#endif

#if DATA_EXPORT_FORMAT == EXPORT_JSON
char pkt_mac[20] = {0};
inline void data_export(void *ctx, wifi_csi_info_t *data)
{
	/*
	 * Halfway house between CSV and Base64 encoded binary data.
	 * Records are exported in as JSON decodeable strings.
	 * All fields are exported as text representations except the CSI array which is Base64 encoded binary data.
	 * This reduces the transmitted record length and it maintains most fields in human-parseable forms.
	 */
	gettimeofday(&tv_now, NULL);
	memset(crecord, 0, CRECORD_LENGTH);
	wifi_csi_info_t csi_info = data[0];
	wifi_pkt_rx_ctrl_t rx_ctrl = csi_info.rx_ctrl;
	rx_timestamp = rx_ctrl.timestamp;

	sprintf(pkt_mac, "%02X:%02X:%02X:%02X:%02X:%02X", csi_info.mac[0], csi_info.mac[1], csi_info.mac[2], csi_info.mac[3], csi_info.mac[4], csi_info.mac[5]);
	std::stringstream ss;

	ss << "["
	   << BOM << ","
	   << data_export_format << ","
	   << csi_export_format << ","
	   << (int)project_type << ","
	   << this_mac_str << ","
	   << tv_now.tv_sec << ","
	   << tv_now.tv_usec << ","
	   << rx_ctrl.timestamp << ","
	   << pkt_mac << ","
	   << rx_ctrl.rssi << ","
	   << rx_ctrl.rate << ","
	   << rx_ctrl.sig_mode << ","
	   << rx_ctrl.mcs << ","
	   << rx_ctrl.cwb << ","
	   << rx_ctrl.smoothing << ","
	   << rx_ctrl.not_sounding << ","
	   << rx_ctrl.aggregation << ","
	   << rx_ctrl.stbc << ","
	   << rx_ctrl.fec_coding << ","
	   << rx_ctrl.sgi << ","
	   << rx_ctrl.noise_floor << ","
	   << rx_ctrl.ampdu_cnt << ","
	   << rx_ctrl.channel << ","
	   << rx_ctrl.secondary_channel << ","
	   << rx_ctrl.timestamp << ","
	   << rx_ctrl.ant << ","
	   << rx_ctrl.sig_len << ","
	   << rx_ctrl.rx_state << ","
	   << data->first_word_invalid
		? 1
		: 0 << ","
			<< data->len << ",\"";

	memcpy(crecord, data->buf, data->len);
	base64encode();
	ss << hrecord << "\"," << rx_ctrl.timestamp << "]\n";
	printf(ss.str().c_str());
	fflush(stdout);
}
#endif

#if DATA_EXPORT_FORMAT == EXPORT_CSV
inline void data_export(void *ctx, wifi_csi_info_t *data)
{
	/*
	 * Slightly modified version of the original CSV export.
	 */
	long sys_timestamp = get_steady_clock_timestamp();
	std::stringstream ss;

	wifi_csi_info_t d = data[0];
	char mac[20] = {0};
	sprintf(mac, "%02X:%02X:%02X:%02X:%02X:%02X", d.mac[0], d.mac[1], d.mac[2], d.mac[3], d.mac[4], d.mac[5]);

	ss << "CSI_DATA,"
	   << project_type << ","
	   << mac << ","
	   << sys_timestamp << ","
	   // https://github.com/espressif/esp-idf/blob/9d0ca60398481a44861542638cfdc1949bb6f312/components/esp_wifi/include/esp_wifi_types.h#L314
	   << d.rx_ctrl.rssi << ","
	   << d.rx_ctrl.rate << ","
	   << d.rx_ctrl.sig_mode << ","
	   << d.rx_ctrl.mcs << ","
	   << d.rx_ctrl.cwb << ","
	   << d.rx_ctrl.smoothing << ","
	   << d.rx_ctrl.not_sounding << ","
	   << d.rx_ctrl.aggregation << ","
	   << d.rx_ctrl.stbc << ","
	   << d.rx_ctrl.fec_coding << ","
	   << d.rx_ctrl.sgi << ","
	   << d.rx_ctrl.noise_floor << ","
	   << d.rx_ctrl.ampdu_cnt << ","
	   << d.rx_ctrl.channel << ","
	   << d.rx_ctrl.secondary_channel << ","
	   << d.rx_ctrl.timestamp << ","
	   << d.rx_ctrl.ant << ","
	   << d.rx_ctrl.sig_len << ","
	   << d.rx_ctrl.rx_state << ","
	   << real_time_set << ","
	   << get_steady_clock_timestamp() << ","
	   << data->len << ",[";

	int data_len = data->len;
	int8_t *my_ptr;

	my_ptr = data->buf;
	for (int i = 0; i < data_len; i++)
	{
		ss << (int)my_ptr[i] << " ";
	}
	ss << "]\n";
	printf(ss.str().c_str());
	fflush(stdout);
}
#endif

#if DATA_EXPORT_FORMAT == EXPORT_NOP
inline void data_export(void *ctx, wifi_csi_info_t *data)
{
	/*
	 * Do next to nothing, but do it well -- Usefull for perfromance monitoring.
	 */
	taskYIELD();
}
#endif

#ifdef ENABLE_SUMMARY_STATS
static auto interval_timestamp = std::chrono::steady_clock::now();
static auto performance_timestamp = std::chrono::steady_clock::now();
static uint32_t pkt_counter = 0;
static uint32_t report_interval = 4096;
#endif

void export_csi(void *ctx, wifi_csi_info_t *data)
{
	xSemaphoreTake(mutex, portMAX_DELAY);
	#ifdef ENABLE_SUMMARY_STATS
	std::chrono::duration<long, std::micro> dt1 = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - performance_timestamp);
	performance_timestamp = std::chrono::steady_clock::now();
	#endif
	data_export(ctx, data);
	#ifdef ENABLE_SUMMARY_STATS
	++pkt_counter;
	std::chrono::duration<long, std::micro> dt2 = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - performance_timestamp);
	ESP_LOGI(TAG, "{ \"msgid\":1, \"dt since last call\":%ld, \"export data dt\":%ld }\n", dt1.count(), dt2.count());
	if (pkt_counter > report_interval)
	{
		std::chrono::duration<long, std::micro> dt = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - interval_timestamp);
		ESP_LOGI(TAG, "{ \"msgid\":2, \"pkt_counter\":%d, \"per packet dt\":%f, \"Minimum free heap size\": \"%d\" }\n", pkt_counter, (double)dt.count() / pkt_counter, esp_get_minimum_free_heap_size());
		pkt_counter = 0;
		interval_timestamp = std::chrono::steady_clock::now();
	}
	performance_timestamp = std::chrono::steady_clock::now();
	#endif
	xSemaphoreGive(mutex);
}

void csi_init(uint8_t type)
{
	project_type = type;

	ESP_ERROR_CHECK(esp_wifi_set_csi(1));
	wifi_csi_config_t configuration_csi;
	configuration_csi.lltf_en = 1;
	configuration_csi.htltf_en = 1;
	configuration_csi.stbc_htltf2_en = ENABLE_STBC_HTLTF;
	configuration_csi.ltf_merge_en = 0;
	configuration_csi.channel_filter_en = 0;
	configuration_csi.manu_scale = 0;

	ESP_ERROR_CHECK(esp_wifi_set_csi_config(&configuration_csi));
	ESP_ERROR_CHECK(esp_efuse_mac_get_default(this_mac));
#if DATA_EXPORT_FORMAT == EXPORT_JSON || DATA_EXPORT_FORMAT == EXPORT_CSV
	sprintf(this_mac_str, "%02X:%02X:%02X:%02X:%02X:%02X", this_mac[0], this_mac[1], this_mac[2], this_mac[3], this_mac[4], this_mac[5]);
#endif
	ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(&export_csi, NULL));
}

#endif // ESP32_CSI_CSI_COMPONENT_H
