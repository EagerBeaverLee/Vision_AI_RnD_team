
library(tidyverse)

setwd("D:/업무/2024/Artificial_Intteligence/coding/R/AIS_data_analysis")


#ais <- read.csv('AIS_Korea_Dec_08.csv')
#ais_dec_08 <- ais


ais_data_cleaning <- function(df, threshold= 10, layer_name) {
  
  #extracting fields that are needed for visualization
  large_data <- df %>% select(ship_and_cargo_type, name, mmsi, timestamp, course, speed, longitude, latitude)
  
  #creating "shiptype" column
  large_data <- large_data %>% 
    mutate(SHIPTYPE = case_when(ship_and_cargo_type == "70" | ship_and_cargo_type == "71" | 
                                  ship_and_cargo_type == "79" ~ "Cargo",
                                ship_and_cargo_type == "80" ~ "Tanker",
                                ship_and_cargo_type == "52" ~ "Tug",
                                ship_and_cargo_type == "30" ~ "Fishing",
                                ship_and_cargo_type == "60" ~ "Passenger",
                                ship_and_cargo_type == "50" ~ "Pilot",
                                .default = "Other"))
  
  #creating a xy_coords field to delete duplicate coordinates
  large_data <- large_data %>% 
    mutate(lon = round(longitude, 3),
           lat = round(latitude, 3),
           xy_combined = paste(as.character(lon), ", ",
                               as.character(lat))) %>% select(-c(lon, lat))
  
  
  #split a dataset into a large list by mmsi
  split <- split(large_data, large_data$mmsi)
  
  #a function that removes duplicate timestamps
  f_time <- function(x) x[!duplicated(x[,c("timestamp")]),]
  
  #a function that removes duplicate cy_coords
  f_xy <- function(x) x[!duplicated(x[,c("xy_combined")]),]
  
  #applying timestamp removing function
  split <- lapply(split, f_time)
  
  #applying xy_coords removing function
  split <- lapply(split, f_xy)
  
  #converting a large list back into a dataframe again
  large_data <- do.call(what="rbind", split) %>% select(-xy_combined)
  
  #selecting necessary fields in a right order
  large_data <- large_data %>% select(SHIPTYPE, name, mmsi, timestamp, course, speed, longitude, latitude)
  
  #Rename columns
  colnames(large_data) <- c("SHIPTYPE","SHIPNAME", "MMSI", "TIMESTAMP", "COURSE", "SPEED", "LONGITUDE", "LATITUDE")
  
  #creating "HIGHER_TYPE" & "RADAR" & "SONAR" fields
  #the following fields are created as they are needed in the model developed for the NAVY   
  large_data <- large_data %>% mutate(HIGHER_TYPES = case_when(SHIPTYPE == "Cargo" ~ "FIRST",
                                                               SHIPTYPE == "Tanker" ~ "SECOND",
                                                               SHIPTYPE == "Tug" ~ "THIRD",
                                                               SHIPTYPE == "Fishing" ~ "FOURTH",
                                                               SHIPTYPE == "Passenger" ~ "FIFTH",
                                                               SHIPTYPE == "Pilot" ~ "SIXTH",
                                                               .default = "OTHER")) %>%
    mutate(RADUIS = case_when(SHIPTYPE == "Cargo" ~ 15000,
                              SHIPTYPE == "Tanker" ~ 12000,
                              SHIPTYPE == "Tug" ~ 10000,
                              SHIPTYPE == "Fishing" ~ 8000,
                              SHIPTYPE == "Passenger" ~ 7000,
                              SHIPTYPE == "Pilot" ~ 6000,
                              .default = 5000)) %>% 
    
    mutate(SONAR = case_when(SHIPTYPE == "Cargo" ~ 12000,
                             SHIPTYPE == "Tanker" ~ 9000,
                             SHIPTYPE == "Tug" ~ 7000,
                             SHIPTYPE == "Fishing" ~ 5000,
                             SHIPTYPE == "Passenger" ~ 4000,
                             SHIPTYPE == "Pilot" ~ 3000,
                             .default = 2000)) 
  
  #removing ', ' from the shipname field
  large_data$SHIPNAME <- gsub(","," ", large_data$SHIPNAME)
  
  #ordering the data by MMSI & TIMESTAMP
  large_data <- large_data %>% arrange(MMSI, TIMESTAMP)
  
  #counting number of points per MMSI
  count <- large_data %>% group_by(MMSI) %>% count() %>% arrange(n)
  
  #Inner_join count data to large data, then filtering mmsi whose total count is greater than or equal to 10 
  large_data <- large_data %>% inner_join(count, by=join_by(MMSI)) %>% filter(n>threshold) %>% select(-n)
  
  #writing a cleaned ais data unto Global Environment with a new name
  assign(layer_name, large_data, envir = .GlobalEnv)
  
  #Compare before and after
  comparison <- function(data1, data2) {
    
    before <- dim(data1)[1]
    after <- dim(data2)[1]
    
    diff <- before - after 
    
    cat("the total row number of the input dataset is", dim(data1)[1], '\n')
    cat("the total row number of the output dataset is", dim(data2)[1], '\n')
    cat("the difference between the two dataset is", diff)
  }
  
  comparison(df, large_data)
  
} 


#ais_data_cleaning(ais_dec_08, threshold = 10, "Dec_08_NEW_DATA")

#write.csv(Dec_08_NEW_DATA, file = "cleaned_data/Dec_08_NEW_DATA.csv", row.names = FALSE)

library(tidyverse)

# 1. 전처리된 파일을 저장할 폴더 생성 (없으면 생성)
output_folder <- "cleaned_data"
if (!dir.exists(output_folder)) {
  dir.create(output_folder)
}

# 2. 작업할 파일 리스트 가져오기 
# AIS_Korea_Dec_ 뒤에 08부터 14까지 숫자가 붙은 csv 파일.
file_list <- list.files(pattern = "AIS_Korea_Dec_(0[1-9]|1[0-4])\\.csv$")

# 3. 반복문을 이용한 순차 처리
for (file_name in file_list) {
  
  cat("현재 처리 중인 파일:", file_name, "\n")
  
  # (1) 데이터 불러오기
  temp_df <- read_csv(file_name)
  
  # (2) 새 레이어 이름 설정 (확장자 제거 및 _NEW_DATA 접미사)
  new_layer_name <- paste0(tools::file_path_sans_ext(file_name), "_NEW_DATA")
  
  # (3) 기존에 정의한 전처리 함수 실행 
  # 함수 내부에 assign()이 있으므로 전역 환경에도 생성되지만, 
  # 저장을 위해 함수 실행 후 해당 객체를 가져옴
  ais_data_cleaning(temp_df, threshold = 10, layer_name = new_layer_name)
  
  # (4) 전역 환경에 생성된 데이터를 가져와서 csv로 저장
  cleaned_data <- get(new_layer_name)
  write_csv(cleaned_data, file.path(output_folder, paste0(new_layer_name, ".csv")))
  
  cat("저장 완료:", file.path(output_folder, paste0(new_layer_name, ".csv")), "\n\n")
}

cat("모든 파일의 전처리가 완료되었습니다.")




