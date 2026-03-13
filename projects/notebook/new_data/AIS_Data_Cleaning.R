




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


ais_data_cleaning(Dec_01, threshold = 10, "Dec_01_NEW_DATA")